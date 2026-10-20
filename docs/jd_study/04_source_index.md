# 源码符号索引

生成日期：2026-09-25。由 Python AST 静态生成，未导入研究模块。覆盖根目录 Python 文件及 data、factors、eval、alpha、portfolio、backtest、products、validation、live、sector_panic、governance、scripts、tests、configs 下 Python 文件。排除缓存、outputs、虚拟环境与临时目录。

**本索引仅用于定位，不代表全部源码已逐行审计或已完成学习。行号是生成时快照。**

使用方法：先在核心精读中确定链路，再查文件/函数；测试清单是用例定义，不是测试通过记录。浏览当前源码不能替代冻结运行的 source manifest。

扫描 528 个 Python 文件，记录 6241 个顶层函数或直接类方法，解析失败 0。

## alpha/__init__.py

[打开文件](../../alpha/__init__.py)

无顶层函数/类；阅读模块常量、导入或入口逻辑。

## alpha/direct_state_allocator.py

[打开文件](../../alpha/direct_state_allocator.py)

- L35 `class DirectStateAllocator`
- L44 `DirectStateAllocator.__init__(self, config: dict)`
- L95 `DirectStateAllocator._validate_and_warn(self)`
- L107 `DirectStateAllocator.compute_sleeve_weights(self, features: pd.DataFrame, available_sleeves: Optional[Dict[int, List[str]]]=None)`
- L196 `DirectStateAllocator._compute_pit_thresholds(self, features: pd.DataFrame)`
- L225 `DirectStateAllocator._evaluate_rules(self, feature_row: pd.Series, thresholds: pd.DataFrame, trade_date: int, warmup_ready: bool=True)`
- L270 `DirectStateAllocator._build_base_weights(self)`
- L283 `DirectStateAllocator._apply_constraints(self, weights: Dict[str, float], available: Optional[List[str]], trade_date: int)`
- L345 `DirectStateAllocator._apply_floor(self, weights: Dict[str, float])`
- L368 `DirectStateAllocator._apply_cap(self, weights: Dict[str, float])`
- L400 `DirectStateAllocator._apply_smoothing(self, weights: Dict[str, float])`
- L441 `_compute_rolling_quantile(values: np.ndarray, min_warmup: int=52, quantile: float=0.75)`

## alpha/factor_alignment.py

[打开文件](../../alpha/factor_alignment.py)

- L58 `align_factors_to_signal_dates(factor_dfs: Dict[str, pd.DataFrame], signal_dates: List[int], alignment_config: Optional[dict]=None, trade_dates: Optional[List[int]]=None)`
- L159 `_align_single_factor(df: pd.DataFrame, value_col: str, signal_dates: List[int], max_stale_days: int, trade_dates: Optional[List[int]], factor_name: str='')`
- L256 `_count_trading_days_between(from_date: int, to_date: int, trade_dates: List[int])`
- L267 `_calendar_days_between(from_date: int, to_date: int)`
- L278 `_find_value_column(df: pd.DataFrame, factor_name: str='')`

## alpha/factor_gating.py

[打开文件](../../alpha/factor_gating.py)

- L33 `evaluate_factor_coverage_at_date(factor_df: pd.DataFrame, fwd_returns_df: pd.DataFrame, signal_date: int, lookback_months: int=12, horizon: int=5, trade_dates: Optional[Sequence[int]]=None, min_date_coverage: float=0.7, min_stocks_per_date: int=30, min_merge_rate: float=0.3, expected_dates: Optional[Sequence[int]]=None)`
- L228 `_find_fwd_ret_col(fwd_returns_df: pd.DataFrame)`

## alpha/factor_pruning.py

[打开文件](../../alpha/factor_pruning.py)

- L26 `class FactorPruner`
- L39 `FactorPruner.__init__(self, factor_dfs: Dict[str, pd.DataFrame], fwd_rets: pd.DataFrame, signal_dates: List[int], enabled_factors: Optional[List[str]]=None)`
- L61 `FactorPruner.analyze(self)`
- L116 `FactorPruner._analyze_single(self, fname: str, factor_df: pd.DataFrame, horizon_col: str)`
- L212 `FactorPruner._compute_rank_autocorr(self, factor_df: pd.DataFrame)`
- L253 `FactorPruner._period_mean_ic(self, factor_df: pd.DataFrame, horizon_col: str, date_filter)`
- L282 `FactorPruner._decide_action(self, fname: str, analysis: Dict[str, Any])`
- L343 `FactorPruner.generate_pruned_config(self, output_path: Optional[Path]=None)`
- L398 `FactorPruner.generate_report(self)`

## alpha/ic_weighting.py

[打开文件](../../alpha/ic_weighting.py)

- L36 `class ICWeighting`
- L44 `ICWeighting.__init__(self, ic_window_months: int=12, shrinkage: float=0.3, weight_cap: float=0.3, min_ic_obs: int=20, min_icir: float=0.0, hard_cap: bool=False, horizon: int=5, min_active_factors: int=1, coverage_gate_enabled: bool=False, sign_stability_check: bool=True, ic_method: str='rank', factor_whitelist: Optional[List[str]]=None, factor_blacklist: Optional[List[str]]=None, **kwargs)`
- L82 `ICWeighting._min_factors_for_cap(self)`
- L98 `ICWeighting._filter_factors(self, factor_dfs: Dict[str, pd.DataFrame])`
- L115 `ICWeighting.compute_rolling_ic(self, factor_dfs: Dict[str, pd.DataFrame], forward_returns_df: pd.DataFrame, horizon: int=5, min_stocks: int=30)`
- L183 `ICWeighting.compute_weights(self, ic_df: pd.DataFrame, signal_date: int, eligible_factor_names: Optional[List[str]]=None, trade_dates: Optional[List[int]]=None)`
- L319 `ICWeighting._apply_hard_cap(self, weights: Dict[str, float])`
- L384 `ICWeighting.compute_composite_score(self, factor_dfs: Dict[str, pd.DataFrame], ic_df: pd.DataFrame, signal_date: int, fwd_returns_df: 'pd.DataFrame | None'=None, trade_dates: 'list[int] | None'=None, expected_dates: 'list[int] | None'=None)`
- L528 `ICWeighting.compute_composite_series(self, factor_dfs: Dict[str, pd.DataFrame], forward_returns_df: pd.DataFrame, signal_dates: List[int], horizon: 'int | None'=None)`

## alpha/ml_alpha.py

[打开文件](../../alpha/ml_alpha.py)

- L27 `class MLAlphaModel`
- L44 `MLAlphaModel.__init__(self, model_type: str='gradient_boosting', model_params: Optional[dict]=None, target_horizon: int=5, purge_days: int=5, embargo_days: int=60)`
- L63 `MLAlphaModel._build_model(self)`
- L85 `MLAlphaModel.prepare_data(self, factor_dfs: Dict[str, pd.DataFrame], forward_returns_df: pd.DataFrame, start_date: Optional[int]=None, end_date: Optional[int]=None)`
- L162 `MLAlphaModel.walk_forward_train(self, factor_dfs: Dict[str, pd.DataFrame], forward_returns_df: pd.DataFrame, dates: List[int], n_initial_train: int=252, n_retrain: int=63)`
- L271 `MLAlphaModel.predict(self, factor_dfs: Dict[str, pd.DataFrame], date: int)`
- L322 `MLAlphaModel.evaluate_walk_forward(self, results: List[Dict])`
- L359 `MLAlphaModel.feature_importance(self)`

## alpha/regime_allocator.py

[打开文件](../../alpha/regime_allocator.py)

- L29 `class RegimeAllocator`
- L38 `RegimeAllocator.__init__(self, config: dict)`
- L58 `RegimeAllocator.compute_sleeve_weights(self, regime_probs: pd.DataFrame, available_sleeves: Optional[Dict[int, List[str]]]=None, sleeve_multipliers: Optional[pd.DataFrame]=None)`
- L145 `RegimeAllocator._prepare_multipliers(self, sleeve_multipliers: Optional[pd.DataFrame])`
- L157 `RegimeAllocator._apply_multipliers(self, raw_weights: np.ndarray, trade_date: int, multiplier_indexed: Optional[pd.DataFrame])`
- L183 `RegimeAllocator._apply_constraints(self, weights: Dict[str, float], available: Optional[List[str]], trade_date: int)`
- L244 `RegimeAllocator._apply_floor(self, weights: Dict[str, float])`
- L272 `RegimeAllocator._apply_cap(self, weights: Dict[str, float])`
- L310 `RegimeAllocator._apply_smoothing(self, weights: Dict[str, float])`
- L360 `RegimeAllocator._build_mapping_matrix(self, regime_weights: dict)`
- L395 `_find_prob_columns(df: pd.DataFrame, regime_names: List[str])`

## alpha/regime_composite.py

[打开文件](../../alpha/regime_composite.py)

- L24 `class RegimeCompositeBuilder`
- L34 `RegimeCompositeBuilder.__init__(self, min_sleeves: int=2)`
- L41 `RegimeCompositeBuilder.build(self, sleeve_scores: Dict[str, pd.DataFrame], sleeve_weights: pd.DataFrame)`
- L118 `RegimeCompositeBuilder._build_date(self, trade_date: int, sleeve_scores: Dict[str, pd.DataFrame], weights_indexed: pd.DataFrame, weight_cols: List[str])`
- L191 `RegimeCompositeBuilder._cross_sectional_zscore(composite: pd.DataFrame)`

## alpha/regime_detector.py

[打开文件](../../alpha/regime_detector.py)

- L39 `class RegimeDetector`
- L55 `RegimeDetector.__init__(self, config: dict)`
- L117 `RegimeDetector.compute_features(self, index_df: pd.DataFrame, prices_df: Optional[pd.DataFrame], signal_dates: Sequence[int])`
- L187 `RegimeDetector.predict_regime_probs(self, features: pd.DataFrame)`
- L231 `RegimeDetector._compute_trend_features(self, idx_pit: pd.DataFrame)`
- L288 `RegimeDetector._compute_volatility_features(self, idx_pit: pd.DataFrame)`
- L317 `RegimeDetector._compute_breadth_features(self, prices_df: Optional[pd.DataFrame], signal_date: int)`
- L406 `RegimeDetector._compute_turnover_features(self, idx_pit: pd.DataFrame)`
- L435 `RegimeDetector._features_to_regime_scores(self, features: pd.DataFrame)`
- L514 `RegimeDetector._pit_normalize_features(self, features: pd.DataFrame)`
- L569 `RegimeDetector._features_to_regime_scores_v2(self, features_norm: pd.DataFrame)`
- L652 `RegimeDetector._compute_value_rotation_scores(self, features_norm: pd.DataFrame)`
- L748 `RegimeDetector._load_auxiliary_index_data(self, end_date: str='20241231')`
- L836 `RegimeDetector._softmax(scores: pd.DataFrame, temperature: float=1.0)`
- L868 `load_regime_config(config_path: str='configs/regime.yaml')`

## alpha/score_to_mu.py

[打开文件](../../alpha/score_to_mu.py)

- L30 `class ScoreToMu`
- L37 `ScoreToMu.__init__(self, method: str='rolling_ic', rolling_ic_window: int=60, vol_window: int=60, regression_window: int=252, regression_min_obs: int=60)`
- L52 `ScoreToMu.calibrate(self, scores: pd.DataFrame, score_col: str='composite_score', forward_returns_df: Optional[pd.DataFrame]=None, horizon: int=5, trade_dates: Optional[List[int]]=None)`
- L112 `ScoreToMu._calibrate_rolling_ic(self, scores: pd.DataFrame, score_col: str, forward_returns_df: pd.DataFrame, horizon: int, trade_dates: Optional[List[int]]=None)`
- L227 `ScoreToMu._calibrate_regression(self, scores: pd.DataFrame, score_col: str, forward_returns_df: pd.DataFrame, horizon: int, trade_dates: Optional[List[int]]=None)`
- L296 `ScoreToMu._rank_only(self, scores: pd.DataFrame, score_col: str)`

## alpha/sleeve_performance_overlay.py

[打开文件](../../alpha/sleeve_performance_overlay.py)

- L27 `class SleevePerformanceOverlay`
- L36 `SleevePerformanceOverlay.__init__(self, config: dict)`
- L51 `SleevePerformanceOverlay.compute_multipliers(self, sleeve_scores: Dict[str, pd.DataFrame], fwd_returns: pd.DataFrame, signal_dates: Sequence[int], trade_dates: Sequence[int] | None=None)`
- L106 `SleevePerformanceOverlay._compute_ic_history(self, sleeve_scores: Dict[str, pd.DataFrame], fwd_returns: pd.DataFrame, ret_col: str)`
- L150 `SleevePerformanceOverlay._score_sleeve_window(self, ic_history: pd.DataFrame, sleeve: str, signal_date: int, lookback_start: int, cutoff: int | None)`
- L214 `SleevePerformanceOverlay._quality_score(self, icir: float, hit_rate: float)`
- L229 `SleevePerformanceOverlay._neutral_multipliers(self, signal_dates: Sequence[int])`

## alpha/strategy_sleeves.py

[打开文件](../../alpha/strategy_sleeves.py)

- L31 `class StrategySleeveEngine`
- L42 `StrategySleeveEngine.__init__(self, sleeve_config: dict, composite_params: dict)`
- L70 `StrategySleeveEngine._validate_and_warn(self)`
- L135 `StrategySleeveEngine.compute_sleeve_scores(self, factor_dfs: Dict[str, pd.DataFrame], fwd_returns: pd.DataFrame, signal_dates: List[int])`
- L215 `StrategySleeveEngine.get_available_sleeves_by_date(self, sleeve_scores: Dict[str, pd.DataFrame])`

## alpha/time_utils.py

[打开文件](../../alpha/time_utils.py)

- L27 `matured_ic_cutoff(signal_date: int, horizon: int, trade_dates: Sequence[int])`
- L69 `trading_days_in_window(trade_dates: Sequence[int], start_date: int, end_date: int)`
- L99 `calendar_month_lookback_start(signal_date: int, months: int)`
- L121 `matured_lookback_window(signal_date: int, horizon: int, lookback_months: int, trade_dates: Sequence[int])`

## backtest/__init__.py

[打开文件](../../backtest/__init__.py)

无顶层函数/类；阅读模块常量、导入或入口逻辑。

## backtest/cost_model.py

[打开文件](../../backtest/cost_model.py)

- L27 `class CostConfig`
- L51 `CostConfig.from_yaml(cls, config: dict)`
- L76 `CostConfig.stress_2x(self)`
- L95 `class CostModel`
- L102 `CostModel.__init__(self, config: Optional[CostConfig]=None)`
- L108 `CostModel.compute_trade_cost(self, ts_code: str, side: str, price: float, shares: int, amount: Optional[float]=None, adv_amount: Optional[float]=None)`
- L190 `CostModel.compute_turnover_cost(self, prev_weights: pd.Series, new_weights: pd.Series, prices: pd.Series, portfolio_value: float, adv_amount: Optional[pd.Series]=None)`
- L284 `CostModel.compute_net_return(self, gross_return: float, buy_cost_bps: float, sell_cost_bps: float)`

## backtest/execution.py

[打开文件](../../backtest/execution.py)

- L23 `daily_vwap_from_raw(df: pd.DataFrame)`
- L30 `implementation_shortfall(exec_price: pd.Series, vwap: pd.Series)`
- L37 `shrink_buys_until_cash_covers(prev: pd.Series, executed: pd.Series, cost_frac_fn, tradable: Optional[pd.Series]=None, max_iter: int=24)`
- L89 `class ExecutionSimulator`
- L96 `ExecutionSimulator.__init__(self, cost_model=None, tradable_mask=None, execution_price: str='open', round_lot: bool=True, min_unit: int=100, t1_sell_restriction: bool=True)`
- L111 `ExecutionSimulator.cost_model(self)`
- L118 `ExecutionSimulator.tradable(self)`
- L127 `ExecutionSimulator.execute_rebalance(self, signal_date: int, target_weights: pd.Series, prev_holdings: pd.Series, prices: pd.DataFrame, portfolio_value: float, can_buy: Optional[pd.Series]=None, can_sell: Optional[pd.Series]=None)`
- L282 `ExecutionSimulator.compute_period_return(self, weights: pd.Series, prices_start: pd.Series, prices_end: pd.Series, dividends: Optional[pd.Series]=None, missing_as_zero: bool=False)`
- L325 `ExecutionSimulator.generate_orders(self, signal_date: int, prev_weights: pd.Series, target_weights: pd.Series, prices: pd.DataFrame, portfolio_value: float)`

## backtest/portfolio_backtester.py

[打开文件](../../backtest/portfolio_backtester.py)

- L31 `class PortfolioBacktester`
- L49 `PortfolioBacktester.__init__(self, universe_builder=None, execution_simulator=None, cost_model=None, tradable_mask=None, panel_loader=None, config: Optional[dict]=None)`
- L69 `PortfolioBacktester.universe(self)`
- L76 `PortfolioBacktester.execution(self)`
- L83 `PortfolioBacktester.cost_model(self)`
- L90 `PortfolioBacktester.tradable(self)`
- L97 `PortfolioBacktester.loader(self)`
- L106 `PortfolioBacktester.run_backtest(self, scores: pd.DataFrame, score_col: str='composite_score', start_date: str='20160101', end_date: Optional[str]=None, top_n: int=50, weighting: str='equal', rebalance_freq: str='weekly', initial_capital: float=100000000.0, benchmark_code: str='000300.SH', cost_multiplier: float=1.0, slippage_bps: Optional[float]=None, weight_max: float=0.02, mu_df: Optional[pd.DataFrame]=None, entry_rank: Optional[int]=None, exit_rank: Optional[int]=None, turnover_max: Optional[float]=None, turnover_penalty: Optional[float]=None, no_trade_band: float=0.0, max_weight_change: Optional[float]=None, score_smoothing_halflife: Optional[int]=None, hold_buffer_mode: str='standard', cost_aware_lambda: float=0.0, estimated_cost_bps: float=10.0, cov_shrinkage: str='ledoit_wolf', constraint_relaxation: str='none', return_diagnostics: bool=False)`
- L295 `PortfolioBacktester._simulate(self, scores: pd.DataFrame, score_col: str, signal_dates: List[int], top_n: int, weighting: str, initial_capital: float, mu_df: Optional[pd.DataFrame]=None, weight_max: float=0.02, end_date: Optional[int]=None, entry_rank: Optional[int]=None, exit_rank: Optional[int]=None, turnover_max: Optional[float]=None, turnover_penalty: Optional[float]=None, no_trade_band: float=0.0, max_weight_change: Optional[float]=None, score_smoothing_halflife: Optional[int]=None, hold_buffer_mode: str='standard', cost_aware_lambda: float=0.0, estimated_cost_bps: float=10.0, cov_shrinkage: str='ledoit_wolf', constraint_relaxation: str='none')`
- L668 `PortfolioBacktester._compute_metrics(self, portfolio_values: List[Dict], benchmark_returns: pd.DataFrame, holdings_log: List[Dict], trades_log: List[Dict], opt_diagnostics: Optional[Dict]=None)`
- L848 `PortfolioBacktester._compute_data_quality_gate(metrics: Dict[str, Any])`
- L940 `PortfolioBacktester._load_benchmark_returns(self, benchmark_code: str, start_date: str, end_date: str)`
- L986 `PortfolioBacktester._compute_benchmark_stats(self, strategy_returns: pd.Series, benchmark_returns: pd.DataFrame, period_dates: Optional[pd.DataFrame]=None)`
- L1129 `PortfolioBacktester._smooth_scores(day_scores, score_col, signal_date, halflife: int)`
- L1168 `PortfolioBacktester._select_with_buffer(day_scores, score_col, top_n, prev_weights, entry_rank, exit_rank)`
- L1220 `PortfolioBacktester._compute_log_return_matrix(price_window: pd.DataFrame)`
- L1230 `PortfolioBacktester._ensure_psd(Sigma: np.ndarray, epsilon: float=1e-06)`
- L1242 `PortfolioBacktester._compute_optimized_weights(self, top_stocks, score_col, signal_date, prev_weights, exec_date, top_n, mu_df=None, weight_max=0.02, turnover_max=None, turnover_penalty=None)`
- L1459 `PortfolioBacktester._get_execution_prices(self, ts_codes: List[str], date_str: str)`
- L1474 `PortfolioBacktester._compute_holding_return(self, weights: pd.Series, exec_date: int, next_exec_date: int)`
- L1527 `PortfolioBacktester.generate_report(self, results: Dict[str, Any], run_id: str=None)`

## configs/__init__.py

[打开文件](../../configs/__init__.py)

无顶层函数/类；阅读模块常量、导入或入口逻辑。

## configs/factor_config.py

[打开文件](../../configs/factor_config.py)

- L27 `load_factor_config(config_path: Optional[str]=None)`
- L81 `_default_config()`
- L89 `_default_composite_params()`
- L106 `_build_composite_params(raw: dict)`
- L123 `validate_regime_sleeve_factors(regime_config: Dict[str, Any], factor_config: Dict[str, Any])`
- L189 `validate_candidate_policy(factor_config: Dict[str, Any])`

## data/__init__.py

[打开文件](../../data/__init__.py)

无顶层函数/类；阅读模块常量、导入或入口逻辑。

## data/adjust.py

[打开文件](../../data/adjust.py)

- L23 `class PriceAdjuster`
- L34 `PriceAdjuster.__init__(self, client=None)`
- L39 `PriceAdjuster.client(self)`
- L48 `PriceAdjuster.load_adj_factors(self, ts_codes: Optional[List[str]]=None, start_date: Optional[str]=None, end_date: Optional[str]=None, force_reload: bool=False)`
- L87 `PriceAdjuster.compute_adj_prices(self, raw_prices: pd.DataFrame, adj_factor_df: Optional[pd.DataFrame]=None, missing_threshold: float=0.02, strict: bool=True)`
- L214 `PriceAdjuster.compute_forward_returns(prices: pd.DataFrame, horizons: List[int]=[1, 5, 10, 20])`
- L250 `PriceAdjuster.get_prices_for_factors(self, ts_codes: List[str], start_date: str, end_date: str, fields: Optional[List[str]]=None)`
- L298 `PriceAdjuster.get_prices_for_trading(self, ts_codes: List[str], date: str)`
- L331 `PriceAdjuster.get_signal_returns(self, ts_codes: List[str], signal_dates: List[str], forward_horizon: int=5)`
- L380 `validate_adj_prices(adj_prices: pd.DataFrame, raw_prices: Optional[pd.DataFrame]=None, daily_return_threshold: float=5.0, weekly_return_threshold: float=10.0)`
- L640 `get_adjuster(**kwargs)`

## data/ashare_boards.py

[打开文件](../../data/ashare_boards.py)

- L8 `is_sse_szse_main_board(ts_code: str)`
- L23 `code_allowed_for_board(ts_code: str, board: str=BOARD_SSE_SZSE_MAIN)`

## data/calendar.py

[打开文件](../../data/calendar.py)

- L25 `class TradingCalendar`
- L33 `TradingCalendar.__init__(self, client=None)`
- L47 `TradingCalendar.client(self)`
- L56 `TradingCalendar.load(self, start_date: str='20150101', end_date: str='20991231', force_reload: bool=False)`
- L176 `TradingCalendar.trade_dates(self)`
- L182 `TradingCalendar.is_trade_day(self, date: int)`
- L188 `TradingCalendar.is_trade_day_str(self, date_str: str)`
- L195 `TradingCalendar.next_trade_day(self, date: int, n: int=1)`
- L211 `TradingCalendar.prev_trade_day(self, date: int, n: int=1)`
- L215 `TradingCalendar.first_trade_day_on_or_after(self, date: int)`
- L236 `TradingCalendar.next_trade_day_str(self, date_str: str, n: int=1)`
- L240 `TradingCalendar.prev_trade_day_str(self, date_str: str, n: int=1)`
- L244 `TradingCalendar.trade_days_between(self, start: int, end: int)`
- L251 `TradingCalendar.trade_days_in_range(self, start: str, end: str)`
- L255 `TradingCalendar.count_trade_days(self, start: int, end: int)`
- L262 `TradingCalendar.weekly_rebalance_dates(self, start_date: str, end_date: str, weekday: int=4)`
- L315 `TradingCalendar.monthly_rebalance_dates(self, start_date: str, end_date: str)`
- L349 `int_to_datetime(date_int: int)`
- L355 `datetime_to_int(dt: datetime)`
- L360 `date_range(start: str, end: str, freq: str='W-FRI')`
- L372 `get_calendar(**kwargs)`

## data/industry.py

[打开文件](../../data/industry.py)

- L23 `class IndustryClassifier`
- L36 `IndustryClassifier.__init__(self, client=None)`
- L46 `IndustryClassifier.has_data(self)`
- L52 `IndustryClassifier.classifications(self)`
- L57 `IndustryClassifier.client(self)`
- L66 `IndustryClassifier.load(self, force_reload: bool=False)`
- L125 `IndustryClassifier._load_pit_member(self)`
- L152 `IndustryClassifier._load_from_stock_basic(self, force_reload: bool)`
- L169 `IndustryClassifier._build_pit_lookup(self)`
- L190 `IndustryClassifier.get_industry(self, ts_code: str, date: int)`
- L210 `IndustryClassifier.get_industries(self, ts_codes: List[str], date: int)`
- L223 `IndustryClassifier.get_industry_dummies(self, ts_codes: List[str], date: int)`
- L244 `IndustryClassifier.get_benchmark_industry_weights(self, date: int, universe: List[str], stock_weights: Optional[pd.Series]=None)`
- L274 `IndustryClassifier.get_industry_name(self, industry_code: str)`
- L285 `IndustryClassifier.list_industries(self)`
- L298 `get_industry_classifier(**kwargs)`

## data/limit_price_from_preclose.py

[打开文件](../../data/limit_price_from_preclose.py)

- L16 `tick_round(price: float)`
- L20 `board_limit_ratio(ts_code: str, trade_date: int, is_st: bool=False)`
- L39 `is_st_on_date(ts_code: str, trade_date: int, st_periods: Mapping[str, Sequence[tuple[int, int]]])`
- L50 `limit_prices_from_preclose(pre_close: float, ts_code: str, trade_date: int, is_st: bool=False)`
- L64 `st_periods_from_namechange(namechange: pd.DataFrame)`
- L92 `synthesize_limit_rows(prices: pd.DataFrame, skip_pairs: set[tuple[str, int]] | None=None, st_periods: Mapping[str, Sequence[tuple[int, int]]] | None=None, code_ok=None)`

## data/limit_status_cache.py

[打开文件](../../data/limit_status_cache.py)

- L18 `_normalize_limit_status_df(df: pd.DataFrame)`
- L29 `_month_bounds(year: int, month: int)`
- L41 `write_limit_status_merged(loader, lim_df: pd.DataFrame)`

## data/limit_status_exec_coverage.py

[打开文件](../../data/limit_status_exec_coverage.py)

- L28 `filter_limit_df_to_board(df: pd.DataFrame, board: str=BOARD_SSE_SZSE_MAIN)`
- L40 `signal_exec_pairs(trade_dates: Sequence[int], every: int=5)`
- L55 `pit_members(snapshots: Mapping[int, Sequence[str]], asof: int)`
- L67 `snapshots_from_weights(weights: pd.DataFrame, *, index_col: str='index_code', code_col: str='ts_code', date_col: str='trade_date')`
- L92 `required_limit_pairs(signal_exec: Sequence[tuple[int, int]], index_snapshots: Mapping[str, Mapping[int, Sequence[str]]], index_codes: Sequence[str]=PRODUCT_INDEX_CODES, board: str=BOARD_SSE_SZSE_MAIN)`
- L114 `present_limit_pairs(limit_df: pd.DataFrame, *, code_col: str='ts_code', date_col: str='trade_date')`
- L128 `missing_limit_pairs(required: Iterable[tuple[str, int]], present: Iterable[tuple[str, int]])`
- L135 `exec_dates_with_gaps(missing: Iterable[tuple[str, int]])`
- L139 `coverage_stats(required: Iterable[tuple[str, int]], present: Iterable[tuple[str, int]])`

## data/panel_loader.py

[打开文件](../../data/panel_loader.py)

- L59 `class MemoryMonitor`
- L62 `MemoryMonitor.__init__(self, max_memory_gb: float=8.0, warning_threshold_gb: float=6.0)`
- L69 `MemoryMonitor.current_gb(self)`
- L77 `MemoryMonitor.peak_gb(self)`
- L80 `MemoryMonitor.check(self, label: str='')`
- L100 `MemoryMonitor.report(self)`
- L114 `class PanelLoader`
- L137 `PanelLoader.__init__(self, data_path: str='data/parquet', max_memory_gb: float=8.0, stock_batch_size: int=80, date_chunk_months: int=3, use_float32: bool=True)`
- L156 `PanelLoader.initialize(self)`
- L173 `PanelLoader._register_tables(self)`
- L203 `PanelLoader.query(self, table_name: str, columns: Optional[List[str]]=None, start_date: Optional[str]=None, end_date: Optional[str]=None, ts_codes: Optional[List[str]]=None, extra_where: Optional[str]=None, order_by: Optional[str]=None, limit: Optional[int]=None)`
- L259 `PanelLoader._query_duckdb(self, table_name: str, cols: str, start_date: Optional[str], end_date: Optional[str], ts_codes: Optional[List[str]], extra_where: Optional[str], order_by: Optional[str], limit: Optional[int])`
- L340 `PanelLoader._query_pyarrow(self, table_name: str, columns: Optional[List[str]], start_date: Optional[str], end_date: Optional[str], ts_codes: Optional[List[str]], extra_where: Optional[str]=None)`
- L376 `PanelLoader._scan_fallback(self, path: Path, columns: Optional[List[str]], filters: List[tuple])`
- L407 `PanelLoader.query_prices(self, start_date: str, end_date: str, ts_codes: Optional[List[str]]=None, fields: Optional[List[str]]=None, price_type: str='adj')`
- L434 `PanelLoader.query_daily_basic(self, start_date: str, end_date: str, ts_codes: Optional[List[str]]=None, fields: Optional[List[str]]=None)`
- L447 `PanelLoader.query_limit_data(self, date: str, ts_codes: Optional[List[str]]=None)`
- L458 `PanelLoader.iter_date_chunks(self, start_date: str, end_date: str, months: int=3, fields: Optional[List[str]]=None, ts_codes: Optional[List[str]]=None)`
- L497 `PanelLoader.iter_stock_batches(self, ts_codes: List[str], batch_size: int=None)`
- L508 `PanelLoader.pivot_for_date(self, date: str, ts_codes: Optional[List[str]]=None, fields: Optional[List[str]]=None, price_type: str='adj')`
- L547 `PanelLoader.pivot_for_window(self, start_date: str, end_date: str, ts_codes: Optional[List[str]]=None, field: str='adj_close')`
- L581 `PanelLoader.write_data(self, df: pd.DataFrame, table_name: str, partition_cols: Optional[List[str]]=None, row_group_size: int=200000, compression: str='zstd', compression_level: int=3, dedupe_keys: Optional[List[str]]=None, replace_partitions: bool=False, partition_values: Optional[dict]=None)`
- L649 `PanelLoader.cleanup_legacy_factor_layout(self, factor_name: str, years: list)`
- L679 `PanelLoader.cleanup_all_legacy_factor_layouts(self)`
- L712 `PanelLoader.write_factor(self, df: pd.DataFrame, factor_name: str, partition_by_year: bool=True)`
- L804 `PanelLoader.read_factor(self, factor_name: str, start_date: Optional[str]=None, end_date: Optional[str]=None, ts_codes: Optional[List[str]]=None)`
- L829 `PanelLoader.factor_coverage(self, factor_name: str, start_date: str, end_date: str)`
- L860 `PanelLoader.has_factor_coverage(self, factor_name: str, start_date: str, end_date: str, min_dates: int=12)`
- L880 `PanelLoader.price_coverage(self, table_name: str, start_date: str, end_date: str)`
- L931 `PanelLoader.daily_basic_coverage(self, start_date: str, end_date: str)`
- L991 `PanelLoader._enforce_dtypes(self, df: pd.DataFrame, table_name: str)`
- L1032 `PanelLoader._build_pa_filter(conditions: List[tuple])`
- L1049 `PanelLoader.close(self)`
- L1056 `PanelLoader.__del__(self)`
- L1059 `PanelLoader.__enter__(self)`
- L1063 `PanelLoader.__exit__(self, *args)`
- L1073 `get_loader(**kwargs)`

## data/parquet_cache.py

[打开文件](../../data/parquet_cache.py)

- L61 `class CacheIntegrityError`
- L65 `_calendar_day_delta(d1: int, d2: int)`
- L78 `_validated_open_trade_days(calendar: pd.DataFrame, start_date: int, end_date: int)`
- L122 `_pid_alive(pid: int)`
- L146 `class ParquetCache`
- L149 `ParquetCache.__init__(self, base_path: str='data/parquet', lock_timeout_sec: float=300.0)`
- L155 `ParquetCache._partition_path(self, table_name: str, partition: Optional[Dict[str, str]]=None)`
- L164 `ParquetCache._canonical_files(part_dir: Path)`
- L185 `ParquetCache._lock_path(self, table_name: str)`
- L189 `ParquetCache._acquire_lock(self, table_name: str)`
- L236 `ParquetCache._release_lock(self, table_name: str)`
- L244 `ParquetCache.primary_keys(table_name: str)`
- L247 `ParquetCache._dedup(self, df: pd.DataFrame, table_name: str)`
- L283 `ParquetCache.exists(self, table_name: str, partition: Optional[Dict[str, str]]=None)`
- L287 `ParquetCache.covers_range(self, table_name: str, start_date: str, end_date: str, date_col: str='trade_date')`
- L316 `ParquetCache.covers_range_per_code(self, table_name: str, codes: List[str], start_date: str, end_date: str, date_col: str='trade_date', code_col: str='ts_code')`
- L365 `ParquetCache.coverage_gaps_per_code(self, table_name: str, codes: List[str], start_date: str, end_date: str, date_col: str='trade_date', code_col: str='ts_code')`
- L435 `ParquetCache._expected_trading_days(self, start_date: str, end_date: str)`
- L464 `ParquetCache.read(self, table_name: str, columns: Optional[List[str]]=None, filters: Any=None, partition: Optional[Dict[str, str]]=None)`
- L515 `ParquetCache.write(self, df: pd.DataFrame, table_name: str, partition_cols: Optional[List[str]]=None, row_group_size: int=200000, compression: str='zstd', compression_level: int=3)`
- L550 `ParquetCache._write_partitioned_merge(self, df, table_name, out_path, partition_cols, row_group_size, compression, compression_level)`
- L608 `ParquetCache._write_flat_atomic(self, df, table_name, out_path, row_group_size, compression, compression_level)`
- L646 `ParquetCache.last_date(self, table_name: str, date_col: str='trade_date')`
- L666 `ParquetCache._build_filter(conditions: List[tuple])`
- L687 `ParquetCache._apply_filters_in_memory(df: pd.DataFrame, conditions: List[tuple])`

## data/price_interior_gaps.py

[打开文件](../../data/price_interior_gaps.py)

- L5 `interior_missing_dates(have: set[int], trade_days: set[int], suspend_days: set[int] | None=None)`

## data/shenwan_l1_daily.py

[打开文件](../../data/shenwan_l1_daily.py)

- L14 `sw_daily_to_index_daily(df: pd.DataFrame)`
- L37 `contracted_l1_codes()`

## data/tradable.py

[打开文件](../../data/tradable.py)

- L30 `_finite_positive(value)`
- L38 `class TradableMask`
- L55 `TradableMask.__init__(self, client=None)`
- L77 `TradableMask.client(self)`
- L86 `TradableMask.load(self, start_date: str='20150101', end_date: Optional[str]=None, force_reload: bool=False)`
- L129 `TradableMask._load_st_flags(self, start_date: str, force_reload: bool)`
- L164 `TradableMask._normalize_suspend_records(self, df: Optional[pd.DataFrame])`
- L201 `TradableMask.get_mask(self, ts_codes: List[str], date: int, raw_prices: Optional[pd.DataFrame]=None, limit_data: Optional[pd.DataFrame]=None)`
- L304 `TradableMask.get_mask_str(self, ts_codes: List[str], date_str: str, **kwargs)`
- L309 `TradableMask.get_mask_batch(self, ts_codes: List[str], dates: List[int], raw_prices_by_date: Optional[Dict[int, pd.DataFrame]]=None)`
- L327 `TradableMask._check_listing_status(self, mask: pd.DataFrame, date: int)`
- L349 `TradableMask._check_new_stock(self, mask: pd.DataFrame, date: int)`
- L367 `TradableMask._check_st(self, mask: pd.DataFrame, date: int)`
- L382 `TradableMask.suspended_codes(self, ts_codes: List[str], date: int)`
- L399 `TradableMask._check_suspend(self, mask: pd.DataFrame, date: int)`
- L423 `TradableMask._check_limits_with_fetch(self, mask: pd.DataFrame, date: int)`
- L439 `TradableMask._check_limits(self, mask: pd.DataFrame, date: int, raw_prices: Optional[pd.DataFrame], limit_data: Optional[pd.DataFrame])`
- L509 `TradableMask._consolidate(self, mask: pd.DataFrame)`
- L518 `TradableMask._cache_mask(self, cache_key: tuple, mask: pd.DataFrame)`
- L526 `TradableMask._augment_limits_from_preclose(self, ts_codes: List[str], date: int, raw_prices: Optional[pd.DataFrame], limit_data: Optional[pd.DataFrame])`
- L564 `TradableMask._fetch_limit_data(self, ts_codes: List[str], date: int)`
- L589 `TradableMask._fetch_raw_open(self, ts_codes: List[str], date: int)`
- L606 `TradableMask.clear_cache(self)`
- L613 `TradableMask.mask_summary(self, mask: pd.DataFrame)`
- L631 `build_tradable_mask_for_date(date: int, ts_codes: List[str], suspend_records: pd.DataFrame, limit_data: pd.DataFrame, stock_basic: pd.DataFrame, st_set: Set[str], ipo_min_days: int=60)`
- L659 `get_tradable(**kwargs)`

## data/tushare_client.py

[打开文件](../../data/tushare_client.py)

- L54 `class RateLimiter`
- L57 `RateLimiter.__init__(self, max_calls_per_minute: int=180)`
- L61 `RateLimiter.wait(self)`
- L68 `RateLimiter.update_rate(self, max_calls_per_minute: int)`
- L75 `with_retry(max_retries: int=5, base_seconds: float=1.0, max_seconds: float=60.0, backoff: float=2.0)`
- L106 `_date_add_days(date_int: int, days: int)`
- L116 `_expected_month_end_dates(start_date: str, end_date: str)`
- L136 `_expected_months(start_date: str, end_date: str)`
- L165 `_merge_index_code_partition(existing_partition: pd.DataFrame, updated_code_rows: pd.DataFrame, index_code: str)`
- L186 `_date_ordinal(value)`
- L197 `class FetchManifest`
- L208 `FetchManifest.__init__(self, cache_path: str)`
- L214 `FetchManifest._acquire_lock(self, timeout_sec: float=30.0)`
- L260 `FetchManifest._release_lock(self)`
- L266 `FetchManifest._load(self)`
- L279 `FetchManifest._save(self)`
- L289 `FetchManifest._save_locked(self)`
- L308 `FetchManifest.record_fetch(self, table: str, start_date: int, end_date: int, codes: list[str] | None=None, per_code_spans: dict[str, tuple[int, int]] | None=None)`
- L352 `FetchManifest._reload_locked(self)`
- L364 `FetchManifest.is_fresh(self, table: str, max_age_days: int=7)`
- L381 `FetchManifest.has_coverage(self, table: str, start_date: int, end_date: int, codes: list[str] | None=None)`
- L421 `FetchManifest.has_coverage_per_code(self, table: str, start_date: int, end_date: int, codes: list[str], lag_tolerance_days: int=10)`
- L487 `FetchManifest.get_coverage_summary(self, table: str)`
- L512 `class TushareClient`
- L528 `TushareClient.__init__(self, cache_path: str='data/parquet', max_requests_per_minute: int=180)`
- L540 `TushareClient._expected_market_codes_by_date(self, trade_dates: list[int | str], expected_codes=None)`
- L660 `TushareClient._expected_active_trade_days_by_code(self, codes: list[str] | set[str], start_date: int | str, end_date: int | str, trade_days: list[int] | set[int] | None=None)`
- L795 `TushareClient._assert_complete_active_code_days(frame: pd.DataFrame, expected_by_code: dict[str, set[int]], context: str)`
- L844 `TushareClient._assert_exact_market_code_sets(frame: pd.DataFrame, expected_by_date: dict[str, set[str]], context: str)`
- L883 `TushareClient._call_api(self, func, **kwargs)`
- L899 `TushareClient.get_daily(self, ts_code: Optional[Union[str, List[str]]]=None, start_date: Optional[str]=None, end_date: Optional[str]=None, fields: Optional[str]=None, use_cache: bool=True, expected_codes=None)`
- L1101 `TushareClient.get_daily_by_trade_dates(self, trade_dates: list, fields: Optional[str]=None, use_cache: bool=True, expected_codes=None)`
- L1248 `TushareClient.get_adj_factor(self, ts_code: Optional[Union[str, List[str]]]=None, start_date: Optional[str]=None, end_date: Optional[str]=None, use_cache: bool=True, batch_size: int=100, allow_partial: bool=False, _write_cache: bool=True)`
- L1756 `TushareClient.get_daily_basic(self, ts_code: Optional[str]=None, trade_date: Optional[str]=None, start_date: Optional[str]=None, end_date: Optional[str]=None, fields: Optional[str]=None, use_cache: bool=True)`
- L1919 `TushareClient.get_index_weight(self, index_code: str='000300.SH', trade_date: Optional[str]=None, start_date: Optional[str]=None, end_date: Optional[str]=None, use_cache: bool=True)`
- L2115 `TushareClient._index_weight_snapshot_sane(frame: pd.DataFrame)`
- L2149 `TushareClient._index_weight_insane_months(cls, frame: pd.DataFrame)`
- L2166 `TushareClient.get_stock_basic(self, exchange: str='', list_status: str='L', fields: Optional[str]=None, use_cache: bool=True)`
- L2237 `TushareClient.get_namechange(self, ts_code: Optional[str]=None, start_date: Optional[str]=None, end_date: Optional[str]=None, use_cache: bool=True)`
- L2313 `TushareClient.get_suspend(self, ts_code: Optional[str]=None, suspend_date: Optional[str]=None, resume_date: Optional[str]=None, start_date: Optional[str]=None, end_date: Optional[str]=None, use_cache: bool=True)`
- L2406 `TushareClient.get_stk_limit(self, ts_code: Optional[str]=None, trade_date: Optional[str]=None, start_date: Optional[str]=None, end_date: Optional[str]=None, use_cache: bool=True, write_cache: bool=True)`
- L2655 `TushareClient.get_trade_cal(self, exchange: str='SSE', start_date: Optional[str]=None, end_date: Optional[str]=None, use_cache: bool=True)`
- L2737 `TushareClient.get_index_daily(self, index_code: str='000300.SH', start_date: Optional[str]=None, end_date: Optional[str]=None, use_cache: bool=True, allow_partial: bool=False)`
- L3071 `TushareClient.get_income(self, ts_code: Optional[str]=None, ann_date: Optional[str]=None, start_date: Optional[str]=None, end_date: Optional[str]=None, period: Optional[str]=None, fields: Optional[str]=None, use_cache: bool=True)`
- L3114 `TushareClient.get_fina_indicator(self, ts_code: Optional[str]=None, ann_date: Optional[str]=None, start_date: Optional[str]=None, end_date: Optional[str]=None, period: Optional[str]=None, fields: Optional[str]=None, use_cache: bool=True)`
- L3156 `TushareClient.get_cashflow(self, ts_code: Optional[str]=None, ann_date: Optional[str]=None, start_date: Optional[str]=None, end_date: Optional[str]=None, period: Optional[str]=None, fields: Optional[str]=None, use_cache: bool=True)`
- L3203 `TushareClient.get_balancesheet(self, ts_code: Optional[str]=None, ann_date: Optional[str]=None, start_date: Optional[str]=None, end_date: Optional[str]=None, period: Optional[str]=None, fields: Optional[str]=None, use_cache: bool=True)`
- L3250 `TushareClient.get_industry(self, level: str='L1', use_cache: bool=True)`
- L3280 `TushareClient.get_fund_basic(self, market: Optional[str]=None, status: str='L', fields: Optional[str]=None, use_cache: bool=True)`
- L3302 `TushareClient.get_fund_daily(self, ts_code: str, start_date: Optional[str]=None, end_date: Optional[str]=None, use_cache: bool=True)`
- L3333 `TushareClient.incremental_update(self, table_name: str, end_date: Optional[str]=None)`
- L3375 `TushareClient._cache_covers_range(self, table_name: str, start_date: Optional[str], end_date: Optional[str], date_col: str='trade_date')`
- L3387 `TushareClient._trading_range(self, start_date: Optional[str], end_date: Optional[str])`
- L3426 `TushareClient._span_covers(lo: int, hi: int, norm_start: int, norm_end: int, normalized: bool)`
- L3437 `TushareClient._expected_trade_days(self, start_date: int, end_date: int)`
- L3488 `TushareClient._assert_full_per_code_range(self, result: pd.DataFrame, codes: list[str], norm_start: int, norm_end: int, normalized: bool, context: str)`
- L3567 `TushareClient._date_filters(start_date: Optional[str], end_date: Optional[str])`
- L3577 `TushareClient._date_code_filters(start_date: Optional[str], end_date: Optional[str], ts_code: Optional[Union[str, List[str]]], date_col: str='trade_date')`
- L3598 `get_client(**kwargs)`

## data/universe.py

[打开文件](../../data/universe.py)

- L32 `index_weight_availability_lag_days(default: int=1)`
- L43 `build_available_constituents(monthly: Dict[int, List[str]], availability_lag_days: int=1, query_end: Optional[str]=None)`
- L109 `pit_constituents_asof(available_constituents: Dict[int, List[str]], date: int)`
- L120 `class UniverseBuilder`
- L136 `UniverseBuilder.__init__(self, client=None, index_code: str='000300.SH', ipo_min_days: int=60, exclude_st: bool=True, availability_lag_days: int=1)`
- L163 `UniverseBuilder.client(self)`
- L172 `UniverseBuilder.load(self, start_date: str='20160101', end_date: Optional[str]=None, force_reload: bool=False)`
- L238 `UniverseBuilder._load_st_history(self, start_date: str, force_reload: bool)`
- L295 `UniverseBuilder._build_monthly_lookup(self)`
- L329 `UniverseBuilder.get_universe(self, date: int)`
- L373 `UniverseBuilder.get_universe_str(self, date_str: str)`
- L377 `UniverseBuilder.get_universe_batch(self, dates: List[int])`
- L394 `UniverseBuilder._get_constituents_at_date(self, date: int)`
- L437 `UniverseBuilder._trading_day_distance(self, start_date: int, end_date: int)`
- L464 `UniverseBuilder._filter_listing_status(self, codes: List[str], date: int)`
- L506 `UniverseBuilder._filter_ipo_window(self, codes: List[str], date: int)`
- L538 `UniverseBuilder._filter_st(self, codes: List[str], date: int)`
- L562 `UniverseBuilder._filter_st_by_name(self, codes: List[str])`
- L594 `UniverseBuilder.constituent_count_history(self, start_date: str, end_date: str)`
- L607 `UniverseBuilder.sample_universe_check(self, n_samples: int=20)`
- L659 `get_universe_builder(**kwargs)`

## eval/__init__.py

[打开文件](../../eval/__init__.py)

无顶层函数/类；阅读模块常量、导入或入口逻辑。

## eval/cs_evaluator.py

[打开文件](../../eval/cs_evaluator.py)

- L25 `class CrossSectionEvaluator`
- L32 `CrossSectionEvaluator.__init__(self, panel_loader=None, min_stocks: int=30)`
- L37 `CrossSectionEvaluator.loader(self)`
- L46 `CrossSectionEvaluator.compute_daily_ic(self, factor_df: pd.DataFrame, factor_col: str, forward_returns_df: pd.DataFrame, horizon: int=5)`
- L118 `CrossSectionEvaluator.ic_summary(self, ic_df: pd.DataFrame, ic_col: str='rank_ic')`
- L159 `CrossSectionEvaluator.ic_by_period(self, ic_df: pd.DataFrame, periods: List[Tuple[int, int]], ic_col: str='rank_ic')`
- L197 `CrossSectionEvaluator.quantile_returns(self, factor_df: pd.DataFrame, factor_col: str, forward_returns_df: pd.DataFrame, horizon: int=5, n_quantiles: int=5)`
- L267 `CrossSectionEvaluator.quantile_summary(self, factor_df: pd.DataFrame, factor_col: str, forward_returns_df: pd.DataFrame, horizon: int=5, n_quantiles: int=5)`
- L313 `CrossSectionEvaluator.compute_turnover(self, factor_df: pd.DataFrame, factor_col: str, top_fraction: float=0.2)`
- L375 `CrossSectionEvaluator.compute_decay(self, factor_df: pd.DataFrame, factor_col: str, forward_returns_df: pd.DataFrame, horizons: List[int]=[1, 5, 10, 20])`
- L398 `CrossSectionEvaluator.evaluate_factor(self, factor_name: str, factor_col: str, factor_df: pd.DataFrame, forward_returns_df: pd.DataFrame, horizons: List[int]=[1, 5, 10, 20], n_quantiles: int=5, periods: Optional[List[Tuple[int, int]]]=None)`
- L448 `CrossSectionEvaluator.evaluate_all_factors(self, factor_dfs: Dict[str, pd.DataFrame], forward_returns_df: pd.DataFrame, **kwargs)`

## eval/factor_report.py

[打开文件](../../eval/factor_report.py)

- L23 `class FactorReport`
- L26 `FactorReport.__init__(self, evaluator=None)`
- L30 `FactorReport.evaluator(self)`
- L39 `FactorReport.report_single_factor(self, factor_name: str, factor_df: pd.DataFrame, forward_returns_df: pd.DataFrame, factor_col: Optional[str]=None)`
- L74 `FactorReport._format_factor_report(self, result: Dict[str, Any])`
- L160 `FactorReport.report_multi_factor(self, factor_results: List[Dict[str, Any]])`
- L223 `FactorReport.report_ic_by_year(self, factor_results: List[Dict[str, Any]], ic_df: pd.DataFrame=None)`
- L260 `FactorReport.report_ic_by_regime(self, factor_results: List[Dict[str, Any]], regimes: list=None)`
- L317 `FactorReport.save_report(self, report: str, filepath: str)`

## factors/__init__.py

[打开文件](../../factors/__init__.py)

无顶层函数/类；阅读模块常量、导入或入口逻辑。

## factors/cross_section.py

[打开文件](../../factors/cross_section.py)

- L28 `class CrossSectionProcessor`
- L39 `CrossSectionProcessor.__init__(self, winsor_method: str='mad', mad_multiplier: float=5.0, quantile_lower: float=0.01, quantile_upper: float=0.99, missing_method: str='industry_median', neutralize: bool=True, neutralizers: Optional[List[str]]=None, standardize_method: str='zscore', min_stocks: int=30)`
- L67 `CrossSectionProcessor.industry(self)`
- L74 `CrossSectionProcessor.loader(self)`
- L80 `CrossSectionProcessor._check_industry_pit(self)`
- L104 `CrossSectionProcessor.process_factor(self, factor_df: pd.DataFrame, factor_name: str, ts_codes: Optional[List[str]]=None, save: bool=True)`
- L169 `CrossSectionProcessor._process_single_date(self, df: pd.DataFrame, date: int, factor_name: str, ts_codes: Optional[List[str]]=None)`
- L211 `CrossSectionProcessor._winsorize(self, series: pd.Series)`
- L235 `CrossSectionProcessor._fill_missing(self, series: pd.Series, date: int)`
- L247 `CrossSectionProcessor._fill_with_industry_median(self, series: pd.Series, date: int)`
- L288 `CrossSectionProcessor._neutralize(self, series: pd.Series, date: int)`
- L373 `CrossSectionProcessor._standardize(self, series: pd.Series)`
- L396 `CrossSectionProcessor.process_all_factors(self, factor_dfs: Dict[str, pd.DataFrame], save: bool=True)`
- L423 `CrossSectionProcessor.compute_forward_returns(prices_df: pd.DataFrame, horizons: List[int]=[1, 5, 10, 20])`
- L460 `create_default_processor()`
- L473 `create_processor_from_config(config_path: str='configs/factors.yaml', section: str=None)`

## factors/factor_panel.py

[打开文件](../../factors/factor_panel.py)

- L26 `class FactorPanelBuilder`
- L34 `FactorPanelBuilder.__init__(self, universe_builder=None, technical_computer=None, fundamental_computer=None, cs_processor=None, panel_loader=None, config: Optional[dict]=None)`
- L51 `FactorPanelBuilder.universe(self)`
- L58 `FactorPanelBuilder.technical(self)`
- L65 `FactorPanelBuilder.fundamental(self)`
- L72 `FactorPanelBuilder.shock_reversal(self)`
- L79 `FactorPanelBuilder.cs(self)`
- L96 `FactorPanelBuilder.shock_cs(self)`
- L135 `FactorPanelBuilder.loader(self)`
- L144 `FactorPanelBuilder.build_panel(self, start_date: str='20160101', end_date: Optional[str]=None, technical_factors: Optional[List[str]]=None, fundamental_factors: Optional[List[str]]=None, signal_frequency: str='weekly', recompute_all: bool=False)`
- L250 `FactorPanelBuilder._get_signal_dates(self, start_date: str, end_date: str, frequency: str)`
- L268 `FactorPanelBuilder._build_universe_map(self, signal_dates: List[int])`
- L279 `FactorPanelBuilder._compute_technical_factors(self, all_stocks: List[str], start_date: str, end_date: str, factor_names: Optional[List[str]], recompute: bool)`
- L310 `FactorPanelBuilder._compute_fundamental_factors(self, all_stocks: List[str], start_date: str, end_date: str, factor_names: Optional[List[str]], recompute: bool)`
- L346 `FactorPanelBuilder._compute_shock_reversal_factors(self, all_stocks: List[str], start_date: str, end_date: str, recompute: bool)`
- L383 `FactorPanelBuilder._compute_and_save_returns(self, all_stocks: List[str], start_date: str, end_date: str, recompute: bool=False)`

## factors/fundamental.py

[打开文件](../../factors/fundamental.py)

- L67 `class FundamentalFactorComputer`
- L76 `FundamentalFactorComputer.__init__(self, panel_loader=None, client=None)`
- L81 `FundamentalFactorComputer.loader(self)`
- L88 `FundamentalFactorComputer.client(self)`
- L97 `FundamentalFactorComputer.compute_daily_basic_factors(self, ts_codes: List[str], start_date: str, end_date: str, factor_names: Optional[List[str]]=None, save: bool=True)`
- L191 `FundamentalFactorComputer.compute_financial_factors(self, ts_codes: List[str], start_date: str, end_date: str, save: bool=True)`
- L295 `FundamentalFactorComputer.compute_all(self, ts_codes: List[str], start_date: str, end_date: str, save: bool=True)`

## factors/shock_reversal.py

[打开文件](../../factors/shock_reversal.py)

- L77 `class ShockReversalComputer`
- L91 `ShockReversalComputer.__init__(self, panel_loader=None, stock_batch_size: int=80, index_code: str='000300.SH')`
- L112 `ShockReversalComputer.loader(self)`
- L121 `ShockReversalComputer.compute_factor(self, ts_codes: List[str], start_date: str, end_date: str, factor_name: str='abnormal_drop_reversal_5', save: bool=True)`
- L209 `ShockReversalComputer.get_filter_stats(self)`
- L216 `ShockReversalComputer._load_market_data(self, start_date: str, end_date: str, beta_window: int)`
- L261 `ShockReversalComputer._load_filter_data(self, start_date: str, end_date: str)`
- L314 `ShockReversalComputer._load_st_periods(self, client, end_date: str)`
- L349 `ShockReversalComputer._compute_batch(self, ts_codes: List[str], start_date: str, end_date: str, factor_name: str, params: dict)`
- L425 `ShockReversalComputer._load_limit_data_batch(self, start_date: str, end_date: str, ts_codes: List[str])`
- L444 `ShockReversalComputer._apply_cross_sectional_amount_filter(self, factor_df: pd.DataFrame, factor_col: str, lookback_start: str, end_date: str, ts_codes: List[str], params: dict)`
- L524 `ShockReversalComputer._compute_stock_factor(self, code: str, price_df: pd.DataFrame, raw_price_df: pd.DataFrame, limit_df: pd.DataFrame, params: dict)`
- L614 `ShockReversalComputer._compute_rolling_beta(self, daily_ret: pd.Series, window: int)`
- L642 `ShockReversalComputer._compute_market_n_day_return(self, n: int)`
- L652 `ShockReversalComputer._apply_limit_down_filter(self, signal: pd.Series, code: str, limit_df: pd.DataFrame, raw_price_df: pd.DataFrame, params: dict)`
- L728 `ShockReversalComputer._apply_suspend_filter(self, signal: pd.Series, code: str)`
- L762 `ShockReversalComputer._apply_st_filter(self, signal: pd.Series, code: str)`
- L794 `ShockReversalComputer._apply_new_stock_filter(self, signal: pd.Series, code: str, params: dict)`
- L834 `ShockReversalComputer._apply_trend_penalty(self, signal: pd.Series, adj_close: pd.Series, beta: pd.Series, params: dict)`
- L885 `_compute_suspend_lookback(start_date: str)`
- L903 `compute_shock_reversal_factor(ts_codes: List[str], start_date: str, end_date: str, save: bool=True)`

## factors/technical.py

[打开文件](../../factors/technical.py)

- L28 `_ema(series: pd.Series, span: int)`
- L33 `_rsi(series: pd.Series, window: int=14)`
- L44 `_macd_hist(series: pd.Series, fast: int=12, slow: int=26, signal: int=9)`
- L54 `_rolling_std(series: pd.Series, window: int)`
- L59 `_rolling_mean(series: pd.Series, window: int)`
- L64 `_rolling_corr(a: pd.Series, b: pd.Series, window: int)`
- L72 `_compute_reversal(adj_close: pd.Series, window: int, skip_recent: int=0)`
- L82 `_compute_momentum(adj_close: pd.Series, window: int, skip_recent: int=20)`
- L92 `_compute_volatility(adj_close: pd.Series, window: int)`
- L98 `_compute_ivol(adj_close: pd.Series, market_return: pd.Series, window: int)`
- L114 `_compute_turnover_ma(turnover_rate: pd.Series, window: int)`
- L119 `_compute_abnormal_turnover(turnover_rate: pd.Series, window: int)`
- L125 `_compute_pv_divergence(adj_close: pd.Series, vol: pd.Series, window: int)`
- L134 `_compute_rsi_factor(adj_close: pd.Series, window: int)`
- L139 `_compute_macd_factor(adj_close: pd.Series, fast: int=12, slow: int=26, signal: int=9)`
- L232 `class TechnicalFactorComputer`
- L252 `TechnicalFactorComputer.__init__(self, panel_loader=None, stock_batch_size: int=80)`
- L257 `TechnicalFactorComputer.loader(self)`
- L266 `TechnicalFactorComputer.compute_factor(self, factor_name: str, ts_codes: List[str], start_date: str, end_date: str, save: bool=True)`
- L341 `TechnicalFactorComputer._compute_factor_batch(self, factor_name: str, ts_codes: List[str], start_date: str, end_date: str, compute_func: Callable, params: dict, data_fields: List[str], func_key: str)`
- L431 `TechnicalFactorComputer.compute_all_factors(self, ts_codes: List[str], start_date: str, end_date: str, factor_names: Optional[List[str]]=None, save: bool=True)`
- L461 `list_technical_factors()`
- L466 `get_factor_spec(factor_name: str)`

## governance/__init__.py

[打开文件](../../governance/__init__.py)

无顶层函数/类；阅读模块常量、导入或入口逻辑。

## live/__init__.py

[打开文件](../../live/__init__.py)

无顶层函数/类；阅读模块常量、导入或入口逻辑。

## live/gated_execution.py

[打开文件](../../live/gated_execution.py)

- L16 `apply_fills_to_book(book: pd.DataFrame, cash: float, fills: pd.DataFrame)`
- L58 `_book_from_lots(shares: dict[str, float], last_price: dict[str, float], cash: float=0.0)`
- L76 `run_gated_step(*, date_str: str, book: pd.DataFrame, inventory: pd.DataFrame, signals: pd.DataFrame, orders: pd.DataFrame, cash: float, broker: Optional[PaperBroker]=None, actual_prices: Optional[pd.DataFrame]=None, data_as_of: Optional[int]=None, **gate_kwargs: Any)`

## live/order_builder.py

[打开文件](../../live/order_builder.py)

- L31 `class OrderBuilder`
- L34 `OrderBuilder.__init__(self, date_str: str, capital: float=100000000.0, min_trade_amount: float=5000.0, round_lot: int=100)`
- L45 `OrderBuilder.load_signals(self)`
- L53 `OrderBuilder.load_previous_holdings(self)`
- L79 `OrderBuilder.get_assumed_prices(self, ts_codes: list)`
- L117 `OrderBuilder.check_tradable(self, ts_codes: list)`
- L148 `OrderBuilder.build_orders(self)`
- L292 `OrderBuilder.save_orders(self, orders: pd.DataFrame)`
- L303 `main()`

## live/paper_broker.py

[打开文件](../../live/paper_broker.py)

- L31 `class PaperBroker`
- L34 `PaperBroker.__init__(self, date_str: str, slippage_tolerance_bps: float=10.0)`
- L39 `PaperBroker.execute(self)`
- L42 `PaperBroker.execute_orders(self, orders: pd.DataFrame, actual_prices: Optional[pd.DataFrame]=None)`
- L126 `PaperBroker._load_orders(self)`
- L134 `PaperBroker._get_actual_prices(self, ts_codes: list)`
- L175 `PaperBroker._log_summary(self, fills: pd.DataFrame)`
- L206 `PaperBroker.save_fills(self, fills: pd.DataFrame, output_dir: str=None)`
- L217 `main()`

## live/photoresist_panic/__init__.py

[打开文件](../../live/photoresist_panic/__init__.py)

无顶层函数/类；阅读模块常量、导入或入口逻辑。

## live/photoresist_panic/common.py

[打开文件](../../live/photoresist_panic/common.py)

- L25 `load_yaml(path: Path | str)`
- L30 `config_hash(config: dict)`
- L36 `wilson_interval(hits: int, n: int, confidence: float=0.95)`
- L48 `validate_frozen_gate(live_config: dict, research_config: dict)`
- L71 `setup_runtime_logger(log_path: Path)`
- L89 `now_iso()`
- L93 `make_run_id(as_of: int)`
- L97 `class RunLock`
- L106 `RunLock.__init__(self, out_dir: Path, run_id: str, stale_after_seconds: int=7200)`
- L114 `RunLock.acquire(self)`
- L151 `RunLock._read_holder(self)`
- L157 `RunLock._age_seconds(self, holder: dict)`
- L164 `RunLock.release(self)`
- L169 `RunLock.__enter__(self)`
- L173 `RunLock.__exit__(self, *exc)`

## live/photoresist_panic/commonality.py

[打开文件](../../live/photoresist_panic/commonality.py)

- L23 `component_snapshot(prices: pd.DataFrame, members: pd.DataFrame, trade_date: int, semi_ret_5d: float | None, limit_status: pd.DataFrame | None=None)`
- L68 `_hit_limit_down(latest_row, code: str, trade_date: int, limit_status: pd.DataFrame | None)`
- L90 `classify_commonality(snapshot: pd.DataFrame, basket_ret_5d: float, config: dict)`
- L156 `dual_commonality(snapshot: pd.DataFrame, eligible_codes: list[str], gate_basket_ret_5d: float, config: dict)`

## live/photoresist_panic/data_updater.py

[打开文件](../../live/photoresist_panic/data_updater.py)

- L32 `yyyymmdd_to_date(day: int)`
- L37 `date_to_yyyymmdd(value: date)`
- L41 `yyyymmdd_add_days(day: int, n: int)`
- L47 `contiguous_ranges(days: list[int], max_gap_calendar_days: int=7)`
- L68 `expected_open_dates(client, start: int, end: int)`
- L80 `latest_closed_trading_day(client, as_of: int)`
- L90 `_month_partition_bounds(year: int, month: int)`
- L96 `_merge_write_partitions(cache, table_name: str, new_rows: pd.DataFrame, partition_cols: list[str], key_cols: list[str]=['ts_code', 'trade_date'])`
- L160 `_cached_dates(cache, table_name: str, code: str, start: int, end: int)`
- L172 `security_update_plan(cache, table_name: str, code: str, open_dates: list[int])`
- L194 `update_stock_prices(client, codes: list[str], open_dates: list[int])`
- L254 `update_indices(client, index_codes: list[str], open_dates: list[int])`
- L291 `update_limit_status(client, codes: list[str], open_dates: list[int])`
- L321 `fetch_suspend_records(client, codes: list[str], days: list[int])`
- L351 `load_local_suspend_records(cache, codes: list[str], start: int, end: int)`
- L373 `build_data_gap_report(client, core_codes: list[str], index_codes: list[str], open_dates: list[int], fetch_missing_suspends: bool=True)`
- L431 `repair_duplicate_keys(cache, table_name: str, codes: list[str], start: int, end: int, partition_cols: list[str])`
- L461 `run_incremental_update(core_codes: list[str], index_codes: list[str], as_of: int, enabled: bool=True, continuity_lookback_trading_days: int=250)`

## live/photoresist_panic/journal.py

[打开文件](../../live/photoresist_panic/journal.py)

- L32 `idempotency_key(gate_version: str, trade_date: int | None, signal_id: str | None, transition_kind: str)`
- L37 `class TransitionJournal`
- L40 `TransitionJournal.__init__(self, path: Path)`
- L47 `TransitionJournal._load(self)`
- L64 `TransitionJournal.records(self)`
- L67 `TransitionJournal.has(self, key: str)`
- L70 `TransitionJournal.append(self, record: dict)`
- L92 `transition_record(gate_version: str, run_id: str, transition: dict, extra: dict | None=None)`
- L115 `event_record(gate_version: str, run_id: str, trade_date: int | None, kind: str, detail: dict | None=None)`
- L129 `entry_resolution_record(gate_version: str, run_id: str, signal: dict, resolution: dict, revision: int=0)`
- L169 `initialization_checkpoint_record(gate_version: str, run_id: str, state: PanicState, proof: dict)`
- L196 `_transitions(records: list[dict])`
- L201 `rebuild_state(records: list[dict])`
- L238 `rebuild_registry(records: list[dict])`
- L279 `rebuild_history(records: list[dict], default_as_of: int | None=None)`
- L323 `verify_state_against_journal(state: PanicState, records: list[dict])`

## live/photoresist_panic/market_utils.py

[打开文件](../../live/photoresist_panic/market_utils.py)

- L8 `build_trading_calendar(prices: pd.DataFrame)`
- L15 `is_st_stock(ts_code: str, stock_status: pd.DataFrame | None, trade_date: int | None=None, namechange: pd.DataFrame | None=None)`
- L78 `compute_amount_rolling_avg(prices: pd.DataFrame, window: int=20, min_periods: int=10)`

## live/photoresist_panic/notifier.py

[打开文件](../../live/photoresist_panic/notifier.py)

- L34 `should_push(transition_kind: str, config: dict)`
- L42 `class DeliveryLog`
- L45 `DeliveryLog.__init__(self, path: Path)`
- L54 `DeliveryLog._load(self)`
- L80 `DeliveryLog.delivered(self, key: str)`
- L83 `DeliveryLog.terminal_status(self, key: str)`
- L86 `DeliveryLog.attempt_count(self, key: str)`
- L89 `DeliveryLog.pending_retries(self)`
- L92 `DeliveryLog.record(self, key: str, channel: str, status: str, response: str, payload_summary: str='', final_status: str | None=None, payload_title: str | None=None, payload_markdown: str | None=None)`
- L130 `refresh_daily_files(alert: dict, markdown: str, out_dir: Path, files: dict)`
- L142 `push_webhook(delivery_log: DeliveryLog, idempotency_key: str, title: str, markdown: str, config: dict)`
- L170 `retry_pending(delivery_log: DeliveryLog, config: dict, max_retries: int=5)`
- L194 `journal_notification_outbox(records: list[dict], config: dict)`
- L220 `dispatch_journal_outbox(delivery_log: DeliveryLog, records: list[dict], config: dict, max_retries: int=5)`
- L250 `suppress_journal_outbox(delivery_log: DeliveryLog, records: list[dict], config: dict)`
- L271 `_post_webhook(url: str, markdown: str)`
- L290 `write_failure_file(reason: str, detail: dict, out_dir: Path)`

## live/photoresist_panic/outcome_tracker.py

[打开文件](../../live/photoresist_panic/outcome_tracker.py)

- L62 `resolve_entry(prices: pd.DataFrame, calendar: np.ndarray, signal: dict, limit_status: pd.DataFrame | None=None, stock_status: pd.DataFrame | None=None, namechange: pd.DataFrame | None=None, min_components: int=3, entry_liquidity: dict | None=None)`
- L165 `_normalize_liquidity_policy(policy: dict | None)`
- L184 `_entry_input_digest(prices: pd.DataFrame, signal: dict, entry_date: int, limit_status: pd.DataFrame | None, stock_status: pd.DataFrame | None, liquidity_policy: dict | None)`
- L229 `_hit_limit_up(stock_row, code: str, trade_date: int, limit_status: pd.DataFrame | None)`
- L248 `_valuation_grid(prices: pd.DataFrame, codes: list[str], entry_date: int, calendar: np.ndarray, horizon: int, suspend_status: pd.DataFrame | None=None)`
- L362 `evaluate_signal_outcome(prices: pd.DataFrame, calendar: np.ndarray, signal: dict, config: dict, limit_status: pd.DataFrame | None=None, stock_status: pd.DataFrame | None=None, suspend_status: pd.DataFrame | None=None)`
- L507 `update_outcomes(outcomes_path, eligibility_path, prices: pd.DataFrame, calendar: np.ndarray, signals: list[dict], config: dict, limit_status: pd.DataFrame | None=None, stock_status: pd.DataFrame | None=None, suspend_status: pd.DataFrame | None=None)`

## live/photoresist_panic/quality_gate.py

[打开文件](../../live/photoresist_panic/quality_gate.py)

- L27 `_duplicate_key_audit(frame: pd.DataFrame)`
- L40 `_suspended_keys(suspend_records: pd.DataFrame | None)`
- L47 `run_quality_gate(prices: pd.DataFrame, index_prices: pd.DataFrame, active_codes: list[str], as_of: int, config: dict, open_dates: list[int] | None=None, suspend_records: pd.DataFrame | None=None, limit_status: pd.DataFrame | None=None, calendar_latest_trading_day: int | None=None)`

## live/photoresist_panic/renderer.py

[打开文件](../../live/photoresist_panic/renderer.py)

- L7 `_fmt(value, spec: str='.2%', default: str='N/A')`
- L16 `_commonality_block(title: str, block: dict)`
- L33 `render_markdown(alert: dict)`
- L163 `build_conclusion(alert: dict)`

## live/photoresist_panic/reversal.py

[打开文件](../../live/photoresist_panic/reversal.py)

- L21 `market_regime_on(index_prices: pd.DataFrame, trade_date: int, config: dict)`
- L41 `semiconductor_state(index_prices: pd.DataFrame, trade_date: int, semi_code: str='931865.CSI')`
- L58 `assess_reversal_context(regime: str, triggered: bool, config: dict)`

## live/photoresist_panic/runner.py

[打开文件](../../live/photoresist_panic/runner.py)

- L50 `class LiveRunContext`
- L53 `LiveRunContext.__init__(self, live_config_path: Path | str=DEFAULT_LIVE_CONFIG, out_dir: Path | str | None=None)`
- L70 `LiveRunContext.path(self, key: str)`
- L74 `LiveRunContext.journal_path(self)`
- L78 `LiveRunContext.delivery_log_path(self)`
- L86 `evaluate_day(context: LiveRunContext, data: dict, gated: pd.DataFrame, calendar: np.ndarray, trade_date: int, regime_by_date: dict | None=None)`
- L124 `_regime_by_date(index_prices: pd.DataFrame, config: dict)`
- L134 `_alert_status(triggered: bool, severity_level: str, reversal_status: str)`
- L147 `load_verified_state(context: LiveRunContext, journal: TransitionJournal, state_path: Path)`
- L182 `_proven_idle_initialization_checkpoint(gated: pd.DataFrame, eval_day: int, machine_config: dict)`
- L239 `run_daily(as_of: int, live_config_path: Path | str=DEFAULT_LIVE_CONFIG, out_dir: Path | str | None=None, refresh_data: bool=True, init_mode: str | None=None, state_override_path: Path | str | None=None)`
- L275 `_record_pipeline_failure(context: LiveRunContext, run_id: str, as_of: int, error: str, notify_config: dict)`
- L300 `_run_daily_inner(context: LiveRunContext, as_of: int, run_id: str, refresh_data: bool, init_mode: str | None, state_override_path: Path | str | None)`
- L592 `_cache()`
- L597 `_continuity_window(update_report: dict, as_of: int, live: dict)`
- L621 `_handle_blocked(context, journal, delivery, run_id, as_of, eval_day, quality, uni_status, notify_config)`
- L667 `_assemble_alert(context, run_id, as_of, eval_day, state, transitions, final_eval, data, semi_code, quality, uni_status, duplicate_run)`
- L791 `_write_manifest(context, run_id, as_of, eval_day, quality, alert, registry, update_report, init_mode)`
- L819 `_dispatch_notifications(context, journal, delivery, notify_config)`
- L828 `_mark_suppressed(context, journal, delivery, notify_config)`

## live/photoresist_panic/severity.py

[打开文件](../../live/photoresist_panic/severity.py)

- L20 `_finite(value)`
- L24 `classify_severity(triggered: bool, basket_ret_5d: float, historical_percentile: float, active_down_breadth_5d: float | None, active_amount_ratio_20d: float | None, active_limit_down_count: int, config: dict)`

## live/photoresist_panic/signal_engine.py

[打开文件](../../live/photoresist_panic/signal_engine.py)

- L16 `load_market_data(history_start: int, as_of: int, core_codes: list[str], index_codes: list[str])`
- L40 `load_full_prices(history_start: int, as_of: int, core_codes: list[str])`
- L69 `load_full_index_prices(history_start: int, as_of: int, index_codes: list[str])`
- L98 `build_core_basket(data: dict, universe: pd.DataFrame, universe_config: dict, history_start: int, as_of: int)`
- L118 `apply_frozen_gate(core_basket: pd.DataFrame, gate_id: str='primary_5d')`
- L128 `gate_snapshot(gated: pd.DataFrame, trade_date: int)`
- L168 `eligibility_snapshot(prices: pd.DataFrame, active_members_df: pd.DataFrame, trade_date: int, eligibility: dict, calendar, limit_status: pd.DataFrame | None=None, suspend_status: pd.DataFrame | None=None, stock_status: pd.DataFrame | None=None)`
- L266 `active_stress_metrics(prices: pd.DataFrame, active_codes: list[str], trade_date: int, limit_status: pd.DataFrame | None=None, breadth_window: int=5)`

## live/photoresist_panic/state_machine.py

[打开文件](../../live/photoresist_panic/state_machine.py)

- L32 `class PanicState`
- L44 `PanicState.load(cls, path: Path)`
- L54 `PanicState.save(self, path: Path)`
- L63 `step(state: PanicState, trade_date: int, triggered: bool, severity: str, active_max_trading_days: int=20, cooldown_clear_days: int=5)`
- L163 `_snapshot_fields(state: PanicState)`

## live/photoresist_panic/universe.py

[打开文件](../../live/photoresist_panic/universe.py)

- L24 `load_universe_v2(config_path: Path | str)`
- L64 `_validate_universe(universe: pd.DataFrame, meta: dict)`
- L123 `production_approved(universe: pd.DataFrame, as_of: int)`
- L136 `active_members(universe: pd.DataFrame, trade_date: int, pool_types: tuple[str, ...]=('core',), min_pit_confidence: str='medium')`
- L163 `universe_status(universe: pd.DataFrame, as_of: int)`
- L184 `export_snapshot(universe: pd.DataFrame, meta: dict, out_dir: Path)`

## live/risk_gate.py

[打开文件](../../live/risk_gate.py)

- L35 `class RiskGate`
- L38 `RiskGate.__init__(self, date_str: str, max_single_weight: float=0.05, max_industry_deviation: float=0.1, max_turnover: float=0.3, max_order_amount: float=10000000.0, max_data_missing_ratio: float=0.2, signals: Optional[pd.DataFrame]=None, orders: Optional[pd.DataFrame]=None, inventory: Optional[pd.DataFrame]=None, book: Optional[pd.DataFrame]=None, data_as_of: Optional[int]=None)`
- L62 `RiskGate.check(self)`
- L122 `RiskGate._load_signals(self)`
- L131 `RiskGate._load_orders(self)`
- L140 `RiskGate._check_single_weight(self, signals: pd.DataFrame)`
- L161 `RiskGate._check_industry_exposure(self, signals: pd.DataFrame)`
- L218 `RiskGate._check_turnover(self, orders: pd.DataFrame)`
- L249 `RiskGate._check_order_amounts(self, orders: pd.DataFrame)`
- L278 `RiskGate._check_data_freshness(self)`
- L312 `RiskGate._check_duplicate_signals(self, signals: pd.DataFrame)`
- L333 `RiskGate._check_book_inventory(self)`
- L377 `RiskGate._check_missing_data(self, signals: pd.DataFrame, orders: pd.DataFrame)`
- L408 `RiskGate.save_result(self, result: dict, output_dir: str=None)`
- L420 `main()`

## live/run_shadow.py

[打开文件](../../live/run_shadow.py)

- L32 `run_single_date(date_str: str, top_n: int=50, capital: float=100000000.0)`
- L249 `run_shadow_loop(start_date: str, end_date: str, top_n: int=50, capital: float=100000000.0)`
- L336 `main()`

## live/signal_service.py

[打开文件](../../live/signal_service.py)

- L29 `class SignalService`
- L32 `SignalService.__init__(self, date_str: str, top_n: int=50, weight_max: float=0.02)`
- L39 `SignalService.generate_signals(self)`
- L124 `SignalService._get_available_factors(self)`
- L133 `SignalService.save_signals(self, signals: pd.DataFrame, output_dir: str=None)`
- L149 `main()`

## portfolio/__init__.py

[打开文件](../../portfolio/__init__.py)

无顶层函数/类；阅读模块常量、导入或入口逻辑。

## portfolio/constraints.py

[打开文件](../../portfolio/constraints.py)

- L32 `class ConstraintBuilder`
- L40 `ConstraintBuilder.__init__(self, long_only: bool=True, leverage: float=1.0, weight_min: float=0.0, weight_max: float=0.02, industry_deviation_max: float=0.05, stock_deviation_max: float=0.02, turnover_max: float=0.3, min_holdings: int=30, max_holdings: int=100, freeze_untradable: bool=True)`
- L65 `ConstraintBuilder.build_constraints(self, w, n_stocks: int, prev_weights: Optional[np.ndarray]=None, can_trade: Optional[np.ndarray]=None, industry_exposures: Optional[np.ndarray]=None, benchmark_industry_weights: Optional[np.ndarray]=None)`
- L138 `ConstraintBuilder.build_can_trade_mask(can_buy: pd.Series, can_sell: pd.Series, codes: List[str])`
- L153 `ConstraintBuilder.build_industry_matrix(industry_classifier, codes: List[str], date: int)`
- L169 `ConstraintBuilder.get_benchmark_industry_weights(industry_classifier, universe: List[str], date: int, method: str='equal')`

## portfolio/cov_estimator.py

[打开文件](../../portfolio/cov_estimator.py)

- L26 `class CovarianceEstimator`
- L34 `CovarianceEstimator.__init__(self, method: str='ledoit_wolf', window: int=252, min_obs: int=60, shrinkage_target: str='constant_correlation', annualize: bool=True)`
- L51 `CovarianceEstimator.estimate(self, returns_df: pd.DataFrame, ts_codes: Optional[list]=None)`
- L128 `CovarianceEstimator._to_wide(self, returns_df: pd.DataFrame, ts_codes: Optional[list]=None)`
- L169 `CovarianceEstimator._sample_cov(ret_matrix: np.ndarray)`
- L176 `CovarianceEstimator._ledoit_wolf(self, ret_matrix: np.ndarray)`
- L233 `CovarianceEstimator._diagonal_shrink(self, ret_matrix: np.ndarray, factor: float)`
- L275 `CovarianceEstimator._factor_model_cov(self, ret_matrix: np.ndarray)`
- L317 `CovarianceEstimator.corr_to_cov(corr: np.ndarray, vols: np.ndarray)`

## portfolio/optimized_weighting.py

[打开文件](../../portfolio/optimized_weighting.py)

- L43 `make_diag(fallback: bool=False, fallback_reason: str='', used_mu: bool=False, low_optimizer_space: bool=False, solver: str='', relaxation_level: int=0, relaxation_applied: Optional[List[str]]=None)`
- L65 `prepare_mu(mu_df: Optional[pd.DataFrame], signal_date: int, stock_codes: List[str])`
- L97 `estimate_covariance(stock_codes: List[str], exec_date: int, method: str='ledoit_wolf', min_obs: int=60)`
- L164 `_ensure_psd(Sigma: np.ndarray, epsilon: float=1e-06)`
- L181 `check_feasibility(top_n: int, weight_max: float)`
- L209 `solve_with_retries(mu_aligned: np.ndarray, Sigma: np.ndarray, codes: List[str], prev_aligned: np.ndarray, weight_max: float, turnover_max: float, turnover_penalty: float=0.0, risk_aversion: float=1.0, cost_aware_lambda: float=0.0, estimated_cost_bps: float=10.0)`
- L319 `relax_constraints_tiered(mu_aligned: np.ndarray, Sigma: np.ndarray, codes: List[str], prev_aligned: np.ndarray, weight_max: float, turnover_max: float, turnover_penalty: float=0.0, risk_aversion: float=1.0, original_Sigma: Optional[np.ndarray]=None, cost_aware_lambda: float=0.0, estimated_cost_bps: float=10.0)`
- L419 `_enhance_shrinkage(Sigma: np.ndarray, factor: float=0.3)`
- L437 `build_fallback_weights(top_n: int, stock_codes: List[str], prev_weights: Optional[pd.Series]=None, method: str='equal')`
- L481 `compute_optimized_weights(top_stocks: pd.DataFrame, score_col: str, signal_date: int, prev_weights: Optional[pd.Series], exec_date: int, top_n: int, mu_df: Optional[pd.DataFrame]=None, weight_max: float=0.02, turnover_max: Optional[float]=None, turnover_penalty: Optional[float]=None, cost_aware_lambda: float=0.0, estimated_cost_bps: float=10.0, cov_method: str='ledoit_wolf', no_trade_band: float=0.0, max_weight_change: Optional[float]=None, constraint_relaxation: str='none')`
- L642 `_apply_no_trade_band(target_weights: pd.Series, prev_weights: pd.Series, band: float)`
- L666 `_apply_max_weight_change(target_weights: pd.Series, prev_weights: pd.Series, max_change: float)`

## portfolio/optimizer.py

[打开文件](../../portfolio/optimizer.py)

- L32 `class PortfolioOptimizer`
- L46 `PortfolioOptimizer.__init__(self, constraint_builder=None, solver_name: str='ECOS', max_iter: int=10000, tolerance: float=1e-06)`
- L57 `PortfolioOptimizer.constraints(self)`
- L66 `PortfolioOptimizer.optimize_mean_variance(self, mu: np.ndarray, Sigma: np.ndarray, risk_aversion: float=1.0, prev_weights: Optional[np.ndarray]=None, can_trade: Optional[np.ndarray]=None, industry_exposures: Optional[np.ndarray]=None, benchmark_ind_weights: Optional[np.ndarray]=None, turnover_penalty: float=0.0)`
- L198 `PortfolioOptimizer.optimize_risk_parity(self, Sigma: np.ndarray, risk_budget: Optional[np.ndarray]=None, prev_weights: Optional[np.ndarray]=None, can_trade: Optional[np.ndarray]=None)`
- L258 `PortfolioOptimizer.optimize_min_variance(self, Sigma: np.ndarray, prev_weights: Optional[np.ndarray]=None, can_trade: Optional[np.ndarray]=None)`
- L298 `PortfolioOptimizer.optimize_max_sharpe(self, mu: np.ndarray, Sigma: np.ndarray, risk_free_rate: float=0.0, prev_weights: Optional[np.ndarray]=None, can_trade: Optional[np.ndarray]=None)`
- L349 `PortfolioOptimizer._ensure_psd(Sigma: np.ndarray, epsilon: float=1e-06)`

## portfolio/risk.py

[打开文件](../../portfolio/risk.py)

- L26 `class RiskAnalytics`
- L29 `RiskAnalytics.__init__(self, confidence: float=0.95, var_window: int=252, target_volatility: float=0.15, max_drawdown_hard_stop: float=0.25)`
- L41 `RiskAnalytics.compute_metrics(self, returns: pd.Series, weights_history: Optional[pd.DataFrame]=None, annual_factor: float=52.0)`
- L153 `RiskAnalytics.risk_decomposition(self, weights: np.ndarray, Sigma: np.ndarray, factor_exposures: Optional[np.ndarray]=None, specific_risk: Optional[np.ndarray]=None)`
- L201 `RiskAnalytics.exposure_analysis(self, weights: np.ndarray, factor_exposures: pd.DataFrame, benchmark_exposures: Optional[np.ndarray]=None)`
- L237 `RiskAnalytics.vol_scale_weights(self, weights: np.ndarray, Sigma: np.ndarray)`
- L262 `RiskAnalytics.drawdown_analysis(self, returns: pd.Series)`

## products/__init__.py

[打开文件](../../products/__init__.py)

无顶层函数/类；阅读模块常量、导入或入口逻辑。

## products/metrics.py

[打开文件](../../products/metrics.py)

- L14 `annualization_factor(index)`
- L32 `nav_to_annual_returns(nav: pd.Series)`
- L48 `summarize(nav: pd.Series, bench_nav: pd.Series, turnover: pd.Series | None=None, data_quality: dict[str, Any] | None=None)`

## products/return_attribution.py

[打开文件](../../products/return_attribution.py)

- L14 `brinson_bhb(w_p: pd.Series, r_p: pd.Series, w_b: pd.Series, r_b: pd.Series)`
- L46 `industry_panel_returns(stock_ret: pd.Series, stock_w: pd.Series, industry: pd.Series)`
- L69 `official_weight_coverage(official: pd.Series, used_index)`
- L78 `brinson_integrity(coverage: pd.Series, recon_bench: pd.Series, true_index: pd.Series, *, min_coverage: float=0.5, max_mean_abs_err: float=0.005)`
- L101 `lagged_beta(r_p: pd.Series, r_m: pd.Series, window: int=24)`
- L112 `residual_after_beta(r_p: pd.Series, r_m: pd.Series, beta: pd.Series)`
- L116 `neutralize_cross_section(values: pd.Series, groups: Optional[pd.Series]=None, extra: Optional[pd.DataFrame]=None)`
- L152 `rank_ic(factor: pd.Series, forward: pd.Series)`
- L159 `summarize_period_returns(excess: pd.Series, ann_periods: float=52.0)`
- L182 `hold_period_stock_return(prices: pd.DataFrame, start: int, end: int, col: str='adj_close')`
- L209 `finite_hold_period_return(prices: pd.DataFrame, start: int, end: int, col: str='adj_close')`
- L220 `original_weight_coverage(weights: pd.Series, valid_index)`

## products/vehicle_compare.py

[打开文件](../../products/vehicle_compare.py)

- L23 `class CalendarUnverified`
- L27 `vehicle_integrity(*, n_windows: int, n_anomaly: int, replica_status: str, return_coverage_status: str, n_etf_finite: int, n_index_finite: int, calendar_status: str)`
- L76 `main_board_weights(weights: pd.Series)`
- L92 `load_index_weight(index_code: str, root: Path)`
- L113 `asof_weights(panel: pd.DataFrame, date: int)`
- L128 `load_etf_close(root: Path, ts_code: str)`
- L146 `period_return(px: pd.Series | pd.DataFrame, start: int, end: int, expected_dates: Optional[list[int]]=None)`
- L190 `period_return_open(px: pd.Series | pd.DataFrame, start: int, end: int, expected_dates: Optional[list[int]]=None)`
- L220 `weighted_stock_return_with_coverage(prices: pd.DataFrame, weights: pd.Series, start: int, end: int, col: str='adj_close')`
- L254 `weighted_stock_return(prices: pd.DataFrame, weights: pd.Series, start: int, end: int, col: str='adj_close')`
- L267 `_nav_period_return(nav: Optional[pd.Series], start: int, end: int)`
- L279 `compare_hold_windows(windows: list[tuple[int, int]], basket_w_by_date: dict[int, pd.Series], replica_w_by_date: dict[int, pd.Series], etf_px: pd.Series | pd.DataFrame, prices: pd.DataFrame, index_px: Optional[pd.Series]=None, *, price_col: str='adj_close', replica_main_w_by_date: Optional[dict[int, pd.Series]]=None, basket_nav: Optional[pd.Series]=None, expected_dates: Optional[list[int]]=None)`
- L378 `summarize_compare(df: pd.DataFrame)`

## products/weekly_long.py

[打开文件](../../products/weekly_long.py)

- L25 `_local_universe_fn(index_code: str, weight_root: Path | None=None)`
- L70 `weekly_rebalance_dates(trade_dates: list[int], every: int=5)`
- L75 `hold_windows(event_dates: list[int], last_date: int)`
- L102 `resolve_industry_index_codes(cached: Iterable[str] | None=None, sw_codes: list[str] | None=None)`
- L110 `unknown_limit_exposure(target: pd.Series, prev: pd.Series, mask: pd.DataFrame)`
- L129 `_valid_px(series: pd.Series)`
- L134 `apply_cost_from_cash(stock_w: pd.Series, cost_frac: float)`
- L149 `mark_holdings(weights: pd.Series, last_px: pd.Series, px_end: pd.Series, suspended: Iterable[str] | None=None)`
- L189 `drift_holdings(weights: pd.Series, p0: pd.Series, p1: pd.Series, last_px: pd.Series | None=None)`
- L205 `shift_trade_date(dates: list[int], date: int, lag: int)`
- L217 `load_adj_panel(start: str, end: str)`
- L226 `load_raw_panel(start: str, end: str)`
- L235 `attach_adj_open(adj: pd.DataFrame, raw: pd.DataFrame)`
- L261 `adjusted_fill_price(adj: pd.DataFrame, raw: pd.DataFrame, date: int, exec_col: str)`
- L280 `_px_lookup(panel: pd.DataFrame, date: int, col: str)`
- L288 `run_stock_weekly(scores: pd.DataFrame, *, start: str, end: str, index_code: str='000300.SH', top_n: int=50, price_type: str='open', slippage_model: str='fixed_bps', capital: float=100000000.0, apply_tradable: bool=True, tradable=None, board: str=BOARD_SSE_SZSE_MAIN)`
- L511 `run_index_weekly(panel: pd.DataFrame, *, start: str, end: str, top_n: int=4, score_col: str='score', cost_bps: float=4.0, exec_lag: int=0)`
- L636 `benchmark_nav(index_code: str, dates: Iterable[int])`

## run_research.py

[打开文件](../../run_research.py)

- L57 `safe_print(text: str)`
- L85 `_strategy_kwargs_from_args(args)`
- L103 `_merge_strategy_kwargs(args, kwargs: dict)`
- L112 `_build_backtester(start_date: str, end_date: str, loader=None)`
- L131 `_check_phase2_price_quality(loader, start_date: str, end_date: str)`
- L219 `_get_cached_cs_factors()`
- L230 `_select_valid_cs_factors(loader, calendar, start_date: str, end_date: str)`
- L266 `_load_factor_config(config_path=None)`
- L286 `_factors_config_path(args)`
- L295 `_normalize_factor_config(config)`
- L310 `_filter_enabled_factors(factor_names: list, enabled_factors: list | None=None)`
- L334 `_check_formal_candidate_policy(factor_config: dict, config_path: str='configs/factors.yaml')`
- L360 `_load_regime_config_safe(config_path: str='configs/regime.yaml')`
- L373 `_select_regime_candidate_factors(loader, regime_config: dict, start_date: str, end_date: str, factor_config: dict=None)`
- L444 `_validate_shock_factor_requirements(loader, regime_config: dict, all_factors: set, valid: list, start_date: str, end_date: str)`
- L520 `_compute_regime_load_window(start_date: str, end_date: str, regime_config: dict, factor_config: dict=None, calendar=None)`
- L581 `_build_regime_scoring_signal_dates(target_signal_dates: list, data_start_date: str, data_end_date: str, calendar)`
- L634 `build_regime_composite(factor_dfs: dict, fwd_rets, signal_dates_int: list, regime_config_path: str, start_date: str, end_date: str, loader=None, data_start_date: str=None, data_end_date: str=None)`
- L1070 `_add_shock_diagnostics(diagnostics: dict, sleeve_scores: dict, sleeve_weights: pd.DataFrame)`
- L1113 `_invert_available_sleeves(available_sleeves: dict)`
- L1127 `_generate_run_id(args)`
- L1161 `_compute_sha256(file_path: str)`
- L1172 `_compute_factor_list_hash(factor_list: list)`
- L1180 `_write_run_manifest(run_id: str, args, factor_list: list=None, phases_run: list=None, extra: dict=None)`
- L1268 `_write_metrics_summary(run_id: str, phase_name: str, metrics: dict)`
- L1347 `_same_float(a, b, tol: float=1e-12)`
- L1356 `_same_config_value(manifest: dict, key: str, expected_value, default=None)`
- L1368 `_load_matching_phase3_optimized(base_config: dict)`
- L1452 `_dump_regime_diagnostics(results, artifacts_dir, period_diag, phase_name)`
- L1541 `_write_diagnostic_artifacts(run_id: str, phase_name: str, results: dict, portfolio_values: list=None, benchmark_period_returns: dict=None, run_id_override: str=None)`
- L1677 `run_phase0(args)`
- L2204 `run_phase1(args)`
- L2272 `run_phase2(args)`
- L2608 `run_phase3(args)`
- L3163 `run_phase4(args)`
- L3258 `run_phase5(args)`
- L3828 `run_phase5_diagnostics(args)`
- L4028 `run_phase5_experiments(args)`
- L4062 `run_smoke(args)`
- L4335 `run_validate(args)`
- L4496 `main()`

## scripts/_check.py

[打开文件](../../scripts/_check.py)

无顶层函数/类；阅读模块常量、导入或入口逻辑。

## scripts/_patch_oos.py

[打开文件](../../scripts/_patch_oos.py)

无顶层函数/类；阅读模块常量、导入或入口逻辑。

## scripts/analyze_photoresist_take_profit.py

[打开文件](../../scripts/analyze_photoresist_take_profit.py)

- L34 `parse_args()`
- L46 `load_adjusted_ohlc(start: int, end: int, codes: list[str])`
- L75 `build_online_first_trigger_signals(gated: pd.DataFrame, calendar: np.ndarray, max_hold_days: int, cooldown_days: int)`
- L98 `build_last_trigger_signals(path: Path, gate_id: str)`
- L106 `simulate_take_profit(ts_code: str, event: pd.Series, prices: pd.DataFrame, calendar: np.ndarray, horizon: int, target_net: float, round_trip_cost: float, touch_mode: str)`
- L141 `evaluate_signals(signals: pd.DataFrame, prices: pd.DataFrame, core_basket: pd.DataFrame, universe: pd.DataFrame, calendar: np.ndarray, config: dict, limit_status: pd.DataFrame | None, suspend_status: pd.DataFrame | None, stock_status: pd.DataFrame | None)`
- L188 `summarize(trades: pd.DataFrame)`
- L204 `_wilson_interval(hits: int, total: int, z: float=1.96)`
- L216 `summarize_primary_conditions(trades: pd.DataFrame)`
- L239 `generate_report(summary: pd.DataFrame, primary_summary: pd.DataFrame)`
- L262 `main()`

## scripts/analyze_sector_panic_entry_review_buffer_v9.py

[打开文件](../../scripts/analyze_sector_panic_entry_review_buffer_v9.py)

- L27 `_number(value)`
- L33 `analyze(root: Path)`
- L162 `main(argv=None)`

## scripts/analyze_sector_panic_hold_sensitivity.py

[打开文件](../../scripts/analyze_sector_panic_hold_sensitivity.py)

- L81 `_read_runtime_table(name: str)`
- L89 `_fmt(value, digits: int=4)`
- L95 `_output_file_metadata(path: Path)`
- L105 `_output_metadata_ok(root: Path, recorded: dict, required_names: set[str] | None=None)`
- L124 `verify_arm_manifests(root_manifest: dict, holds: list[int], sectors: list[str], runtime_snapshot: VerifiedRuntimeSnapshot | None=None)`
- L210 `_markdown_table(columns: list[str], rows: list[list[str]])`
- L218 `_arm_cell(frame: pd.DataFrame, rule_id: str, split_name: str)`
- L225 `load_arm_ledgers(holds: list[int], sectors: list[str])`
- L249 `verify_events_identical(holds: list[int], sectors: list[str])`
- L293 `load_frozen_paths(sectors: list[str], events_by_sector: dict[str, pd.DataFrame], calendar: np.ndarray)`
- L355 `compute_summary(ledgers: dict[tuple[int, str], pd.DataFrame], holds: list[int], sectors: list[str], calendar: np.ndarray)`
- L388 `compute_paired(ledgers: dict[tuple[int, str], pd.DataFrame], holds: list[int], sectors: list[str], splits: list[str])`
- L450 `compute_aggregates(ledgers: dict[tuple[int, str], pd.DataFrame], holds: list[int], sectors: list[str], splits: list[str])`
- L504 `compute_direction_checks(paired: pd.DataFrame)`
- L525 `compute_curves(ledgers: dict[tuple[int, str], pd.DataFrame], holds: list[int], sectors: list[str], paths_by_sector: dict[str, list[dict]], calendar: np.ndarray)`
- L610 `evaluate_candidates(paired: pd.DataFrame, aggregate: pd.DataFrame, summary: pd.DataFrame, direction_checks: pd.DataFrame, rules: dict)`
- L709 `_curve_table_rows(frame: pd.DataFrame, with_rule_hold: bool)`
- L725 `build_report(context: dict)`
- L957 `main()`

## scripts/assemble_strategy_v1.py

[打开文件](../../scripts/assemble_strategy_v1.py)

- L61 `load_prices(start: str, end: str)`
- L99 `load_factor(fname: str)`
- L120 `load_industry_map()`
- L143 `build_composite(factors: Dict[str, pd.DataFrame], trade_dates: pd.DataFrame)`
- L202 `neutralize_composite(composite: pd.DataFrame, industry_map: pd.DataFrame, mktcap: pd.DataFrame)`
- L262 `build_top_n_portfolio(scores: pd.DataFrame, prices: pd.DataFrame, top_n: int=50, rebalance_freq: str='weekly')`
- L311 `run_backtest(holdings: pd.DataFrame, prices: pd.DataFrame, start: str, end: str, rebalance_freq: str='monthly')`
- L422 `main()`

## scripts/audit_alpha_inputs_v4.py

[打开文件](../../scripts/audit_alpha_inputs_v4.py)

- L43 `_load_factor_cache(factor_name: str, start: str, end: str)`
- L105 `_audit_factor(factor_name: str, df: pd.DataFrame, factor_type: str, start: str, end: str)`
- L236 `_check_data_source_availability(client)`
- L288 `_generate_blocked_factors(factor_specs: list[dict], data_availability: dict, audit_results: list[dict], out_path: Path)`
- L338 `main()`

## scripts/audit_cache.py

[打开文件](../../scripts/audit_cache.py)

- L31 `audit(args)`
- L457 `print_human(results)`
- L482 `main()`

## scripts/audit_factor_data_availability.py

[打开文件](../../scripts/audit_factor_data_availability.py)

- L56 `_resolve_source(source_name: str)`
- L65 `_check_source_exists(source_name: str)`
- L87 `_check_available_fields(source_name: str)`
- L112 `_check_date_coverage(source_name: str)`
- L161 `_guess_date_column(source_name: str)`
- L168 `_columns_to_read(source_name: str, date_col: Optional[str])`
- L181 `_check_formula_implemented(factor_name: str)`
- L233 `_load_universe_factors(universe_path: Path)`
- L242 `audit_factor(factor_spec: dict)`
- L360 `main()`

## scripts/audit_industry_member_pit.py

[打开文件](../../scripts/audit_industry_member_pit.py)

- L25 `_load_member()`
- L43 `_load_csi300_weight_dates()`
- L65 `classify_layout(df: pd.DataFrame)`
- L92 `lookup_semantics(df: pd.DataFrame)`
- L128 `csi300_coverage(member: pd.DataFrame, weights: pd.DataFrame)`
- L162 `equal_vs_count_weights(member: pd.DataFrame, weights: pd.DataFrame)`
- L193 `write_report(report: dict)`
- L246 `main()`

## scripts/audit_phase1_execution_book.py

[打开文件](../../scripts/audit_phase1_execution_book.py)

- L24 `_read(runtime: Path, name: str)`
- L31 `fill_stats(attempts: pd.DataFrame)`
- L66 `overlap_stats(overlap: pd.DataFrame, summary: dict)`
- L87 `independent_vs_combined(daily: pd.DataFrame)`
- L113 `main()`

## scripts/audit_sector_panic_component_avwap_losses.py

[打开文件](../../scripts/audit_sector_panic_component_avwap_losses.py)

- L54 `parse_args(argv=None)`
- L65 `_locked_path(relative: str)`
- L74 `_load_scope(path: Path)`
- L93 `_read_table(root: Path, name: str)`
- L101 `_verify_authoritative(directory: Path, scope: dict)`
- L125 `_suspended_keys(frame: pd.DataFrame)`
- L135 `_atomic_json(path: Path, payload: dict)`
- L151 `_canonical(name: str, frame: pd.DataFrame)`
- L159 `_atomic_csv(path: Path, name: str, frame: pd.DataFrame)`
- L179 `_reconcile_component_pnl(component: pd.DataFrame, events: pd.DataFrame)`
- L191 `_summary(scope: dict, outputs: dict[str, pd.DataFrame], events: pd.DataFrame)`
- L234 `run_single(scope_path: Path, authoritative_dir: Path, runtime_dir: Path, out_dir: Path)`
- L320 `verify_replay(left: Path, right: Path)`
- L341 `main(argv=None)`

## scripts/audit_sector_panic_e2_diagnostic_20260920.py

[打开文件](../../scripts/audit_sector_panic_e2_diagnostic_20260920.py)

- L20 `main()`

## scripts/audit_sector_panic_e2_fill_sample_20260921.py

[打开文件](../../scripts/audit_sector_panic_e2_fill_sample_20260921.py)

- L18 `_load(run_dir: Path, name: str)`
- L22 `_group(results, role)`
- L28 `_summary(rows, fills)`
- L45 `main()`

## scripts/audit_sector_panic_e2_followup_20260921.py

[打开文件](../../scripts/audit_sector_panic_e2_followup_20260921.py)

- L18 `main()`

## scripts/audit_sector_panic_e2_full214.py

[打开文件](../../scripts/audit_sector_panic_e2_full214.py)

- L24 `_load(run: Path, name: str)`
- L31 `_key(row: dict)`
- L35 `_comp(row: dict)`
- L39 `_D(value)`
- L43 `_near(a, b)`
- L50 `audit_denominator(results, contract)`
- L94 `audit_ledger(results, fills, cash, orders)`
- L156 `_fill_identity(fill: dict)`
- L167 `_order_identity(order: dict)`
- L180 `compare_baseline(current, baseline, current_fills=None, baseline_fills=None, current_orders=None, baseline_orders=None)`
- L242 `_holding_span(rec: dict, fills: list[dict])`
- L256 `audit_daily_nav(results, fills, daily_nav, calendar: list[int] | None=None)`
- L329 `_finite_positive(value)`
- L339 `_recomputed_structure_ok(row: dict, comp: dict)`
- L359 `_review_window(calendar: list[int], d0: int, as_of: int | None)`
- L370 `_buy_limit(repair_level, signal_avwap, natr20)`
- L381 `_order_matches_submit(order: dict, date: int, target: int, limit: float | None)`
- L399 `_open_before_match(order: dict, date: int)`
- L410 `_open_after_match(order: dict, date: int)`
- L421 `_nonfill_explained(order: dict, row: dict | None, attempts: list[dict])`
- L446 `audit_confirmed_no_entry(results, components, structure_rows, orders, calendar, next_signal_by_event, attempts=None)`
- L574 `iter_structure_rows(path: Path, wanted: set[tuple])`
- L607 `_trade_calendar(contract: dict)`
- L616 `_next_events(contract: dict)`
- L629 `group_counts(results, fills, contract)`
- L667 `main()`

## scripts/audit_sector_panic_e2_material_20260921.py

[打开文件](../../scripts/audit_sector_panic_e2_material_20260921.py)

- L19 `main()`

## scripts/audit_sector_panic_e2_risk_inputs_20260921.py

[打开文件](../../scripts/audit_sector_panic_e2_risk_inputs_20260921.py)

- L22 `_status_counts(results)`
- L30 `main()`

## scripts/audit_sector_panic_rebuild_delivery_20260920.py

[打开文件](../../scripts/audit_sector_panic_rebuild_delivery_20260920.py)

- L19 `fixture()`
- L25 `snap(engine)`
- L32 `main()`

## scripts/audit_sector_panic_rebuild_followup_20260920.py

[打开文件](../../scripts/audit_sector_panic_rebuild_followup_20260920.py)

- L21 `main()`

## scripts/audit_sector_panic_system_20260920.py

[打开文件](../../scripts/audit_sector_panic_system_20260920.py)

- L24 `fixture(length=45)`
- L39 `slim(result)`
- L44 `run()`

## scripts/audit_sector_panic_v10_max_hold_path.py

[打开文件](../../scripts/audit_sector_panic_v10_max_hold_path.py)

- L39 `parse_args(argv=None)`
- L47 `_locked_path(relative: str)`
- L56 `load_scope(path: Path)`
- L77 `_forbid_frozen_output(out_root: Path, runtime_a: Path)`
- L89 `_pct(value: float, digits: int=2)`
- L95 `_pp(value: float, digits: int=2)`
- L101 `_narrative(interpretation: dict, early_summary: pd.DataFrame)`
- L126 `render_report(*, scope: dict, summary: dict, exit_summary: pd.DataFrame, early_summary: pd.DataFrame, interpretation: dict)`
- L222 `main(argv=None)`

## scripts/audit_sector_phase0b_data.py

[打开文件](../../scripts/audit_sector_phase0b_data.py)

- L42 `parse_args(argv: list[str] | None=None)`
- L51 `_read_table(root: Path, name: str)`
- L59 `_atomic_write_json(path: Path, payload: dict)`
- L77 `_atomic_write_csv(path: Path, frame: pd.DataFrame)`
- L94 `_load_contract(scope_path: Path)`
- L112 `_validate_runtime(runtime_dir: Path, scope_path: Path, audit: dict)`
- L138 `_assert_unique(frame: pd.DataFrame, keys: list[str], label: str)`
- L145 `_index_coverage(index_daily: pd.DataFrame, expected_dates: set[int], codes: list[str])`
- L168 `run(scope_path: Path, runtime_dir: Path, replay_runtime_dir: Path, out_dir: Path)`
- L408 `main(argv: list[str] | None=None)`

## scripts/backtest_compare.py

[打开文件](../../scripts/backtest_compare.py)

- L31 `class Strategy`
- L60 `_run_prefix(year, top_n)`
- L64 `_matching_runs(year, top_n)`
- L77 `_find_existing_run(year, top_n)`
- L83 `_arg_value(args, flag)`
- L92 `_manifest_matches_strategy(run_dir, strategy)`
- L115 `_find_existing_strategy_run(year, top_n, strategy)`
- L122 `run_one(year, strategy, top_n)`
- L162 `extract_metrics(run_dir)`
- L190 `main()`

## scripts/brinson_lowvol_csi300.py

[打开文件](../../scripts/brinson_lowvol_csi300.py)

- L27 `_csi300_weights()`
- L47 `_asof_snapshot(dates: list[int], query: int)`
- L52 `main()`

## scripts/build_alpha_factors_v4.py

[打开文件](../../scripts/build_alpha_factors_v4.py)

- L34 `_resolve_available_date(ann_date: Optional[int], end_date: int, report_type: str='quarterly', f_ann_date: Optional[int]=None)`
- L72 `_detect_report_type(end_date: int)`
- L88 `_compute_technical_skip_momentum(prices: pd.DataFrame, momentum_days: int, skip_days: int)`
- L107 `_compute_risk_adjusted_momentum(prices: pd.DataFrame, momentum_days: int, vol_window: int)`
- L123 `_compute_volume_confirmed_momentum(prices: pd.DataFrame, momentum_days: int, vol_window: int)`
- L140 `_compute_trend_quality(prices: pd.DataFrame, short_window: int, long_window: int)`
- L170 `_compute_liquidity_adjusted_reversal(prices: pd.DataFrame, reversal_days: int=5, liquidity_window: int=20, vol_window: int=20)`
- L214 `_compute_vol_adjusted_reversal(prices: pd.DataFrame, reversal_days: int=20, vol_window: int=60)`
- L234 `_compute_low_beta(prices: pd.DataFrame, window: int=60)`
- L268 `_compute_drawdown_resilience(prices: pd.DataFrame, window: int=60, recovery_window: int=20)`
- L297 `_keep_rebalance_frequency(factor_df: pd.DataFrame, frequency: str)`
- L323 `_smooth_factor_values(factor_df: pd.DataFrame, smooth_window: int)`
- L337 `_compute_low_beta_stable(prices: pd.DataFrame, beta_window: int=120, smooth_window: int=20, frequency: str='monthly')`
- L349 `_compute_drawdown_resilience_stable(prices: pd.DataFrame, window: int=120, recovery_window: int=20, smooth_window: int=10, frequency: str='monthly')`
- L362 `_compute_liquidity_adjusted_reversal_low_turnover(prices: pd.DataFrame, reversal_days: int=5, liquidity_window: int=20, vol_window: int=20, smooth_window: int=3, frequency: str='weekly')`
- L378 `_compute_vol_adjusted_reversal_low_turnover(prices: pd.DataFrame, reversal_days: int=20, vol_window: int=60, smooth_window: int=5, frequency: str='weekly')`
- L391 `_compute_panic_reversal(prices: pd.DataFrame, threshold: float=0.05, direction: str='drop', signal_type: str='bin', frequency: str='weekly')`
- L500 `_compute_fundamental_ttm(fin_data: pd.DataFrame, field: str, value_col: str='value', min_quarters: int=2)`
- L560 `_compute_stability_8q(fin_data: pd.DataFrame, field: str, min_quarters: int=3)`
- L605 `_compute_growth_ttm(fin_data: pd.DataFrame, field: str, min_quarters: int=3)`
- L660 `_compute_earnings_acceleration(fin_data: pd.DataFrame, min_quarters: int=4)`
- L722 `_compute_industry_relative(factor_df: pd.DataFrame, industry_map: pd.DataFrame, factor_name: str, min_industry_stocks: int=10)`
- L776 `_compute_profitability_quality(fin_data: pd.DataFrame, margin_fields: List[str], roe_field: str='roe')`
- L817 `_compute_ocf_to_profit(fin_data: pd.DataFrame)`
- L865 `_compute_accrual_quality(income_data: pd.DataFrame, cashflow_data: pd.DataFrame, balance_data: pd.DataFrame)`
- L925 `_compute_receivable_pressure(income_data: pd.DataFrame, balance_data: pd.DataFrame)`
- L990 `_compute_asset_turnover_from_components(income_data: pd.DataFrame, balance_data: pd.DataFrame)`
- L1043 `_compute_growth_value_match(income_data: pd.DataFrame, daily_data: pd.DataFrame, prices: pd.DataFrame)`
- L1146 `_compute_valuation_reversion_3y(daily_data: pd.DataFrame)`
- L1189 `_compute_quality_value_composite(fina_data: pd.DataFrame, daily_data: pd.DataFrame, prices: pd.DataFrame)`
- L1249 `_compute_dividend_quality(fina_data: pd.DataFrame, daily_data: pd.DataFrame, prices: pd.DataFrame)`
- L1327 `_apply_cs_processing(df: pd.DataFrame, cs_config: dict, industry_map: Optional[pd.DataFrame]=None, mktcap_data: Optional[pd.DataFrame]=None)`
- L1367 `_write_factor_cache(df: pd.DataFrame, factor_name: str, base_path: Path, force: bool=False)`
- L1413 `_write_manifest(factor_name: str, stats: dict, config_sha256: str, base_path: Path)`
- L1440 `_load_price_data(start: str, end: str)`
- L1479 `_load_financial_data(source: str, start: str, end: str)`
- L1529 `_load_industry_map()`
- L1577 `_load_cashflow_data(start: str, end: str)`
- L1611 `_load_balancesheet_data(start: str, end: str)`
- L1645 `_ensure_pit_fields(df: pd.DataFrame, ftype: str, prices: pd.DataFrame)`
- L1678 `_validate_factor_output(df: pd.DataFrame, fname: str, start_date: str, end_date: str)`
- L1782 `_diagnose_empty_factor(fname: str, spec: dict, fina_data: pd.DataFrame, income_data: pd.DataFrame, cashflow_data: pd.DataFrame, balance_data: pd.DataFrame, daily_data: pd.DataFrame, industry_map: pd.DataFrame)`
- L1895 `_factor_uses_static_industry(fname: str, df: pd.DataFrame)`
- L1904 `main()`

## scripts/build_new_factor_families.py

[打开文件](../../scripts/build_new_factor_families.py)

- L225 `_load_prices(start: str, end: str)`
- L258 `_load_daily_basic(start: str, end: str)`
- L291 `_load_income()`
- L310 `_compute_intraday_reversal(prices: pd.DataFrame)`
- L317 `_compute_overnight_reversal(prices: pd.DataFrame)`
- L325 `_compute_amihud_illiq(prices: pd.DataFrame, window: int=20)`
- L337 `_compute_vol_price_divergence(prices: pd.DataFrame, window: int=20)`
- L355 `_compute_vol_squeeze(prices: pd.DataFrame, short: int=10, long: int=60)`
- L370 `_compute_tail_risk(prices: pd.DataFrame, window: int=60)`
- L381 `_compute_avg_field(daily_basic: pd.DataFrame, field: str, window: int)`
- L393 `_compute_std_field(daily_basic: pd.DataFrame, field: str, window: int)`
- L405 `_compute_volume_shock(prices: pd.DataFrame, short: int=5, long: int=20)`
- L419 `_compute_amount_concentration(prices: pd.DataFrame, window: int=20)`
- L433 `_compute_low_vol(prices: pd.DataFrame, window: int=60)`
- L444 `_compute_residual_vol(prices: pd.DataFrame, window: int=60)`
- L473 `_compute_bollinger(prices: pd.DataFrame, window: int=20)`
- L487 `_compute_price_channel(prices: pd.DataFrame, window: int=60)`
- L501 `_compute_rsi_divergence(prices: pd.DataFrame, rsi_window: int=14, div_window: int=5)`
- L520 `_compute_stability_8q_income(income: pd.DataFrame, field: str, min_quarters: int=4)`
- L558 `_compute_margin_trend(income: pd.DataFrame, min_quarters: int=6)`
- L606 `_apply_cs(df: pd.DataFrame)`
- L633 `_write_cache(df: pd.DataFrame, fname: str, force: bool=False)`
- L659 `_write_manifest(fname: str, stats: dict)`
- L680 `main()`

## scripts/build_panic_basket_daily_gate.py

[打开文件](../../scripts/build_panic_basket_daily_gate.py)

- L67 `parse_args()`
- L85 `_normalize(df: pd.DataFrame)`
- L96 `_iter_year_dirs(base: Path, start: int, end: int)`
- L109 `load_prices(root: Path, start: int, end: int)`
- L130 `load_index_prices(root: Path, start: int, end: int)`
- L153 `load_daily_basic(root: Path, start: int, end: int)`
- L178 `load_factor(root: Path, factor_name: str, start: int, end: int)`
- L204 `build_trading_calendar(prices: pd.DataFrame)`
- L208 `trading_day_offset(calendar: np.ndarray, date: int, offset: int)`
- L218 `first_trading_day_of_year(calendar: np.ndarray, year: int)`
- L225 `build_exec_date_map(calendar: np.ndarray, lag: int=1)`
- L232 `_forward_min_window(values: np.ndarray, window: int)`
- L240 `compute_stock_forward_metrics(prices: pd.DataFrame)`
- L277 `assign_ab_labels(df: pd.DataFrame, retention_threshold: float)`
- L302 `compute_market_state_features(prices: pd.DataFrame, index_prices: pd.DataFrame, daily_basic: pd.DataFrame)`
- L410 `build_daily_basket(stock_samples: pd.DataFrame, calendar: np.ndarray, min_stocks: int=MIN_STOCKS_FOR_BASKET, total_stocks_per_day: pd.DataFrame | None=None)`
- L548 `compute_daily_diagnostics(daily_basket: pd.DataFrame)`
- L586 `compute_state_analysis(daily_basket: pd.DataFrame, market_state: pd.DataFrame)`
- L634 `generate_report(daily_basket: pd.DataFrame, diagnostics: pd.DataFrame, state_analysis: pd.DataFrame, args: argparse.Namespace)`
- L734 `main()`

## scripts/build_panic_basket_ml_gate.py

[打开文件](../../scripts/build_panic_basket_ml_gate.py)

- L68 `parse_args()`
- L78 `select_features(train_df: pd.DataFrame)`
- L114 `build_logreg()`
- L131 `run_ml_walkforward(daily_basket: pd.DataFrame)`
- L297 `generate_ml_report(metrics: pd.DataFrame, importance: pd.DataFrame, feature_audit: pd.DataFrame, calibration: pd.DataFrame, audits: list[dict])`
- L408 `main()`

## scripts/build_panic_basket_rule_gate.py

[打开文件](../../scripts/build_panic_basket_rule_gate.py)

- L44 `parse_args()`
- L54 `_rolling_percentile(series: pd.Series, window: int=60)`
- L66 `score_panic_intensity(df: pd.DataFrame)`
- L72 `score_market_stress_inverted(df: pd.DataFrame)`
- L92 `score_breadth_repair(df: pd.DataFrame)`
- L103 `score_liquidity_support(df: pd.DataFrame)`
- L122 `compute_all_scores(df: pd.DataFrame)`
- L134 `evaluate_gate(df: pd.DataFrame, gate_mask: pd.Series, strategy_name: str, window_name: str, raw_ret: float, raw_a_rate: float, threshold_info: str='')`
- L183 `run_walkforward(daily_basket: pd.DataFrame)`
- L269 `generate_rule_report(metrics: pd.DataFrame, audits: list[dict])`
- L365 `main()`

## scripts/build_panic_sleeve_gate_validation.py

[打开文件](../../scripts/build_panic_sleeve_gate_validation.py)

- L67 `parse_args()`
- L77 `_rolling_percentile(series: pd.Series, window: int=60)`
- L89 `score_panic_intensity(df: pd.DataFrame)`
- L95 `score_market_stress_inverted(df: pd.DataFrame)`
- L112 `score_breadth_repair(df: pd.DataFrame)`
- L123 `score_liquidity_support(df: pd.DataFrame)`
- L142 `build_logreg_model()`
- L159 `generate_walkforward_gates(daily_basket: pd.DataFrame)`
- L278 `event_forward_validation(gates: pd.DataFrame)`
- L338 `_legacy_simulate_real_path_sleeve_unused(prices: pd.DataFrame, gates: pd.DataFrame, market_calendar: np.ndarray, event_stock_samples: pd.DataFrame)`
- L508 `simulate_real_path_sleeve(prices: pd.DataFrame, gates: pd.DataFrame, market_calendar: np.ndarray, event_stock_samples: pd.DataFrame)`
- L734 `compute_real_path_metrics(daily_returns: pd.DataFrame)`
- L787 `generate_phase4_report(event_forward: pd.DataFrame, path_metrics: pd.DataFrame, threshold_audit: list[dict], audits: list[dict], daily_returns: pd.DataFrame)`
- L935 `main()`

## scripts/build_photoresist_panic_events.py

[打开文件](../../scripts/build_photoresist_panic_events.py)

- L60 `_promote_builder_outputs(staging_dir: Path, final_dir: Path)`
- L123 `parse_args()`
- L137 `generate_run_id(prefix: str='panic')`
- L146 `load_yaml(path: Path)`
- L151 `collect_not_implemented_features(research_config: dict)`
- L188 `build_pit_universe(universe_config: dict, start: int, end: int)`
- L232 `get_universe_for_date(universe_df: pd.DataFrame, trade_date: int, pool_types: list[str] | None=None, min_pit_confidence: str='low')`
- L259 `_normalize(df: pd.DataFrame)`
- L270 `_safe_dedup(df: pd.DataFrame, keys: list[str] | None=None)`
- L310 `_iter_year_dirs(base: Path, start: int, end: int, margin: int=1)`
- L328 `_clip_loaded_dates(df: pd.DataFrame, start: int, end: int, *, date_col: str='trade_date', warmup_years: int=1)`
- L350 `load_prices(start: int, end: int, ts_codes: list[str])`
- L381 `load_index_prices(start: int, end: int, codes: list[str])`
- L406 `load_daily_basic(start: int, end: int, ts_codes: list[str])`
- L432 `load_limit_status(start: int, end: int, ts_codes: list[str])`
- L455 `load_suspend_status(start: int, end: int, ts_codes: list[str])`
- L481 `load_stock_status()`
- L492 `load_namechange(codes: list[str] | None=None)`
- L525 `build_trading_calendar(prices: pd.DataFrame)`
- L529 `build_calendar_index(calendar: np.ndarray)`
- L534 `trading_day_offset(calendar: np.ndarray, date: int, offset: int)`
- L547 `compute_listing_age(prices: pd.DataFrame, calendar: np.ndarray)`
- L558 `compute_amount_20d_avg(prices: pd.DataFrame)`
- L572 `compute_amount_ratio_20d(prices: pd.DataFrame)`
- L587 `_limit_flag_col(limit_status: pd.DataFrame, side: str)`
- L615 `_is_at_limit(ts_code: str, trade_date: int, side: str, limit_status: pd.DataFrame | None, prices: pd.DataFrame | None=None, tick_tolerance: float=0.005, limit_lookup: dict | None=None)`
- L714 `_build_limit_lookup(limit_status: pd.DataFrame | None, prices: pd.DataFrame | None)`
- L757 `check_consecutive_limit_down(ts_code: str, trade_date: int, limit_status: pd.DataFrame | None, prices: pd.DataFrame, calendar: np.ndarray, n_days: int=2)`
- L790 `is_suspended(ts_code: str, trade_date: int, suspend_status: pd.DataFrame | None, prices: pd.DataFrame)`
- L829 `is_st_stock(ts_code: str, stock_status: pd.DataFrame | None, trade_date: int | None=None, namechange: pd.DataFrame | None=None)`
- L898 `filter_eligible_stocks(day_prices: pd.DataFrame, prices: pd.DataFrame, trade_date: int, calendar: np.ndarray, eligibility: dict | None, listing_age_map: pd.Series | None=None, amt_20d_map: pd.Series | None=None, limit_status: pd.DataFrame | None=None, suspend_status: pd.DataFrame | None=None, stock_status: pd.DataFrame | None=None, namechange: pd.DataFrame | None=None, limit_lookup: dict | None=None, exec_date: int | None=None, exec_prices: pd.DataFrame | None=None)`
- L1007 `build_basket_daily(prices: pd.DataFrame, universe_df: pd.DataFrame, basket_rules: dict, calendar: np.ndarray, start: int, end: int, daily_basic: pd.DataFrame | None=None, limit_status: pd.DataFrame | None=None, suspend_status: pd.DataFrame | None=None, stock_status: pd.DataFrame | None=None, namechange: pd.DataFrame | None=None, eligibility: dict | None=None)`
- L1210 `apply_panic_gate(core_basket: pd.DataFrame, gate_config: dict)`
- L1255 `compute_panic_scores(core_basket: pd.DataFrame, index_prices: pd.DataFrame, score_config: dict)`
- L1329 `classify_events(core_basket: pd.DataFrame, index_prices: pd.DataFrame, intensity_config: dict, environment_config: dict, calendar: np.ndarray, calendar_index: dict, max_cluster_gap: int=5)`
- L1433 `_run_builder(args: argparse.Namespace, out_dir: Path, final_out_dir: Path)`
- L1873 `main()`

## scripts/build_sector_panic_confirmation_close_v10_lifecycle_report.py

[打开文件](../../scripts/build_sector_panic_confirmation_close_v10_lifecycle_report.py)

- L54 `_redirected_records(source: Path, r7_source: Path, runtime: Path)`
- L81 `_augment_records(records: list[dict], source: Path)`
- L132 `_summary(records: list[dict])`
- L156 `_html_page(records_json: str, summary_json: str)`
- L240 `build_report(source: Path, r7_source: Path, runtime: Path, output: Path)`
- L262 `parse_args(argv=None)`
- L271 `main(argv=None)`

## scripts/build_sector_panic_confirmation_invalidation_v11_lifecycle_report.py

[打开文件](../../scripts/build_sector_panic_confirmation_invalidation_v11_lifecycle_report.py)

- L39 `_number(value: object, digits: int=8)`
- L47 `_date(value: object)`
- L52 `_bool(value: object)`
- L56 `_key(row: dict)`
- L65 `_latest(frame: pd.DataFrame)`
- L78 `_load_v10_records(path: Path)`
- L94 `_order(row: dict)`
- L107 `_v11_arm(old_arm: dict, component: dict | None, attempts: list[dict])`
- L179 `_build_records(v10_html: Path, source: Path)`
- L199 `_summary(records: list[dict])`
- L218 `_replace_embedded_payload(html: str, records: list[dict], summary: dict)`
- L236 `_enhance_page(html: str)`
- L329 `build_report(v10_html: Path, source: Path, output: Path)`
- L338 `parse_args(argv=None)`
- L346 `main(argv=None)`

## scripts/build_sector_panic_e2_lifecycle_report.py

[打开文件](../../scripts/build_sector_panic_e2_lifecycle_report.py)

- L39 `_date(value: object)`
- L46 `_float(value: object)`
- L54 `_compact(value: object, digits: int=6)`
- L59 `_bool(value: object)`
- L63 `_key(row: dict[str, str])`
- L67 `_read_rows(path: Path)`
- L72 `_group_by_key(rows: list[dict[str, str]])`
- L81 `_unique_by_key(rows: list[dict[str, str]], ledger: str)`
- L91 `_load_names(path: Path)`
- L101 `_name_at(names: dict[str, list[tuple[str, str, str]]], code: str, date: str)`
- L108 `_operation(date: str, kind: str, label: str, price: object=None, detail: str='', status: str='', order: int=0)`
- L128 `_state_operations(rows: list[dict[str, str]])`
- L158 `_build_records(source_root: Path, runtime_root: Path)`
- L411 `_html_page(payload: str, stats: dict[str, int])`
- L663 `build_report(source_root: Path, runtime_root: Path, output_path: Path)`
- L694 `parse_args(argv: list[str] | None=None)`
- L702 `main(argv: list[str] | None=None)`

## scripts/build_sector_panic_entry_exit_attribution_report.py

[打开文件](../../scripts/build_sector_panic_entry_exit_attribution_report.py)

- L66 `_missing(value: object)`
- L76 `_safe(value: object)`
- L85 `_pct(value: object)`
- L95 `_read(source: Path, name: str)`
- L105 `_workspace_path(relative: object)`
- L114 `_read_json(path: Path, label: str)`
- L124 `_validate_report_scope(scope_path: Path)`
- L161 `_validated_runtime_output(root: Path, manifest: dict, name: str)`
- L176 `_assert_matrix_shape(matrix: pd.DataFrame)`
- L195 `_validate_report_provenance(source: Path, scope_path: Path)`
- L254 `load_report_inputs(source: Path=DEFAULT_SOURCE, *, scope_path: Path=DEFAULT_SCOPE, validate_provenance: bool=True)`
- L279 `_forbid_frozen_write(path: Path)`
- L291 `_ordered(matrix: pd.DataFrame)`
- L305 `_winner(row: dict)`
- L319 `_cell_table(matrix: pd.DataFrame)`
- L353 `_control_appendix(matrix: pd.DataFrame)`
- L368 `_filter_appendix(frame: pd.DataFrame)`
- L378 `build_markdown(inputs: dict)`
- L422 `_table_at(lines: list[str], index: int)`
- L438 `build_html(markdown: str, *, title: str='Sector Panic Entry × Exit Attribution Matrix')`
- L469 `build_report(source: Path=DEFAULT_SOURCE, output: Path=DEFAULT_OUTPUT, html_output: Path | None=DEFAULT_HTML, *, scope_path: Path=DEFAULT_SCOPE)`
- L485 `parse_args(argv=None)`
- L495 `main(argv=None)`

## scripts/build_sector_panic_entry_review_buffer_v9_lifecycle_report.py

[打开文件](../../scripts/build_sector_panic_entry_review_buffer_v9_lifecycle_report.py)

- L61 `_read(path: Path)`
- L65 `_number(value: object, digits: int=8)`
- L73 `_date(value: object)`
- L78 `_bool(value: object)`
- L82 `_key(row: dict)`
- L86 `_latest_rows(frame: pd.DataFrame)`
- L96 `_attempt_info(component: dict | None, attempts: list[dict])`
- L128 `_compact_anchor(row: dict)`
- L140 `_compact_state(row: dict)`
- L151 `_compact_daily(row: dict)`
- L162 `_build_records(source: Path, r7_source: Path, runtime: Path)`
- L253 `_summary(records: list[dict])`
- L265 `_html_page(records_json: str, summary_json: str)`
- L296 `build_report(source: Path, r7_source: Path, runtime: Path, output: Path)`
- L306 `parse_args(argv=None)`
- L315 `main(argv=None)`

## scripts/build_sector_panic_extension_no_chase_v8_report.py

[打开文件](../../scripts/build_sector_panic_extension_no_chase_v8_report.py)

- L49 `_read(path: Path)`
- L53 `_number(value: object, digits: int=8)`
- L61 `_date(value: object)`
- L66 `_key(row: dict)`
- L73 `_arm_record(component: dict | None, attempts: list[dict])`
- L105 `_price_paths(runtime_root: Path, records: list[dict])`
- L127 `_build_records(source: Path, r7_source: Path, runtime: Path)`
- L219 `_summary_payload(source: Path, records: list[dict])`
- L252 `_html_page(records_json: str, summary_json: str)`
- L273 `build_report(source: Path, r7_source: Path, runtime: Path, output: Path)`
- L285 `parse_args(argv=None)`
- L294 `main(argv=None)`

## scripts/build_sector_panic_extension_no_chase_v8_report_r1.py

[打开文件](../../scripts/build_sector_panic_extension_no_chase_v8_report_r1.py)

- L29 `_clean_display_nulls(records: list[dict])`
- L37 `_html_page(records_json: str, summary_json: str)`
- L44 `build_report(source: Path, r7_source: Path, runtime: Path, output: Path)`
- L64 `main(argv=None)`

## scripts/build_sector_panic_natr_stop_cause_presentation.py

[打开文件](../../scripts/build_sector_panic_natr_stop_cause_presentation.py)

- L68 `_sha256(path: Path)`
- L76 `_workspace_path(relative: str)`
- L85 `_load_scope(path: Path)`
- L114 `_verify_outputs(study_root: Path, manifest: dict)`
- L126 `_read_rows(path: Path)`
- L131 `_ymd(value: object)`
- L138 `_ymd_ordinal(value: object)`
- L145 `_num(value: object, default: float=float('nan'))`
- L152 `_compact(value: object, digits: int=4)`
- L159 `_compute_payload(study_root: Path)`
- L1288 `_html_page(payload: dict, scope_id: str, disposition: str)`
- L1295 `build_report(scope_path: Path, study_source: Path, output_path: Path, manifest_path: Path)`
- L1345 `parse_args(argv=None)`
- L1354 `main(argv=None)`

## scripts/build_sector_panic_natr_stop_presentation_v2.py

[打开文件](../../scripts/build_sector_panic_natr_stop_presentation_v2.py)

- L36 `_sha256(path: Path)`
- L44 `_workspace_path(relative: str)`
- L53 `_load_scope(path: Path)`
- L82 `_add_cap20_attribution(records: list[dict], study_root: Path)`
- L117 `_html_page(payload: str, stats: dict[str, int], disposition: str)`
- L172 `build_report(scope_path: Path, e2_source: Path, study_source: Path, runtime_root: Path, output_path: Path, manifest_path: Path)`
- L221 `parse_args(argv=None)`
- L232 `main(argv=None)`

## scripts/build_sector_panic_natr_stop_report.py

[打开文件](../../scripts/build_sector_panic_natr_stop_report.py)

- L46 `_read_rows(path: Path)`
- L51 `_key(row: dict[str, str])`
- L55 `_bool(value: object)`
- L59 `_arm_records(study_root: Path)`
- L79 `_extend_paths(records: list[dict], runtime_root: Path)`
- L128 `_enrich_records(records: list[dict], study_root: Path, runtime_root: Path)`
- L209 `_html_page(payload: str, stats: dict[str, int], disposition: str)`
- L248 `build_report(e2_source: Path, study_source: Path, runtime_root: Path, output_path: Path)`
- L267 `parse_args(argv=None)`
- L276 `main(argv=None)`

## scripts/build_sector_panic_r7_sell_point_report.py

[打开文件](../../scripts/build_sector_panic_r7_sell_point_report.py)

- L24 `_date(value: object)`
- L31 `_float(value: object)`
- L39 `_bool(value: object)`
- L43 `_key(row: dict[str, str])`
- L47 `_read_rows(path: Path)`
- L52 `_load_names(path: Path)`
- L62 `_name_at(names: dict[str, list[tuple[str, str, str]]], code: str, date: str)`
- L71 `_group_by_key(rows: list[dict[str, str]])`
- L79 `_prediction_map(path: Path)`
- L93 `_build_records(source_root: Path, runtime_root: Path)`
- L329 `build_report(source_root: Path, runtime_root: Path, output_path: Path)`
- L363 `_html_page(payload: str, selected: int, filled: int, profitable: int, blocked: int)`
- L507 `main()`

## scripts/build_sector_panic_repair_quality_report.py

[打开文件](../../scripts/build_sector_panic_repair_quality_report.py)

- L44 `_date(value: object)`
- L51 `_number(value: object)`
- L59 `_compact(value: object, digits: int=6)`
- L64 `_bool(value: object)`
- L68 `_key(row: dict)`
- L72 `_read(path: Path)`
- L78 `_operation(date: object, kind: str, label: str, price: object=None, detail: str='', order: int=0)`
- L82 `_state_operations(rows: list[dict])`
- L106 `_arm_record(row: dict | None, attempts: list[dict])`
- L130 `_load_prices(runtime_root: Path, records: list[dict])`
- L171 `_build_records(source_root: Path, runtime_root: Path)`
- L268 `_html_page(payload: str, stats: dict)`
- L333 `build_report(source_root: Path, runtime_root: Path, output_path: Path)`
- L379 `parse_args(argv: list[str] | None=None)`
- L387 `main(argv: list[str] | None=None)`

## scripts/build_sector_panic_sell_point_report.py

[打开文件](../../scripts/build_sector_panic_sell_point_report.py)

- L22 `_date(value: object)`
- L29 `_float(value: object)`
- L37 `_key(row: dict[str, str])`
- L41 `_load_names(path: Path)`
- L51 `_name_at(names: dict[str, list[tuple[str, str, str]]], code: str, date: str)`
- L60 `build_report(source_root: Path, runtime_root: Path, output_path: Path)`
- L252 `_html_page(payload: str, count: int, profitable: int, blocked: int)`
- L361 `main()`

## scripts/build_sector_panic_trade_timeline_r7_report.py

[打开文件](../../scripts/build_sector_panic_trade_timeline_r7_report.py)

- L39 `_clean_date(value: object)`
- L43 `_clean_number(value: object, digits: int=6)`
- L47 `_arm_record(result: dict | None, attempts: list[dict])`
- L102 `_first_operation(state_rows: list[dict], reason: str)`
- L112 `_load_price_paths(runtime_root: Path, records: list[dict], pre_signal_sessions: int=PRE_SIGNAL_SESSIONS)`
- L153 `_add_panic_context(record: dict)`
- L178 `_build_records(source_root: Path, runtime_root: Path)`
- L274 `_summary(records: list[dict], source_root: Path)`
- L319 `_html_page(payload: str, summary: dict)`
- L374 `build_report(source_root: Path, runtime_root: Path, output_path: Path)`
- L388 `parse_args(argv: list[str] | None=None)`
- L396 `main(argv: list[str] | None=None)`

## scripts/build_sector_panic_trade_timing_presentation_v3.py

[打开文件](../../scripts/build_sector_panic_trade_timing_presentation_v3.py)

- L42 `_sha256(path: Path)`
- L50 `_workspace_path(relative: str)`
- L59 `_load_scope(path: Path)`
- L88 `_add_timing_fields(records: list[dict], study_root: Path)`
- L147 `_html_page(payload: str, stats: dict[str, int], disposition: str)`
- L225 `build_report(scope_path: Path, e2_source: Path, study_source: Path, runtime_root: Path, output_path: Path, manifest_path: Path)`
- L277 `parse_args(argv=None)`
- L288 `main(argv=None)`

## scripts/build_sector_panic_v12_evidence_stack.py

[打开文件](../../scripts/build_sector_panic_v12_evidence_stack.py)

- L50 `parse_args(argv=None)`
- L60 `_workspace_path(relative: str)`
- L69 `forbid_frozen_output(out_root: Path)`
- L82 `validate_scoped_paths(scope: dict, *, runtime: Path, v10_source: Path, v11_source: Path, out_root: Path)`
- L118 `load_scope(path: Path)`
- L145 `_json_safe(value)`
- L157 `_read_csv(path: Path)`
- L161 `_load_calendar(runtime: Path)`
- L168 `_runtime_end_date(runtime: Path)`
- L176 `render_report(*, scope: dict, summary: dict, audit: pd.DataFrame, counts: dict, diagnostic: dict)`
- L281 `run(scope_path: Path, runtime: Path, v10_source: Path, v11_source: Path, out_root: Path)`
- L400 `main(argv=None)`

## scripts/build_sector_panic_v8_trade_lifecycle_report.py

[打开文件](../../scripts/build_sector_panic_v8_trade_lifecycle_report.py)

- L30 `_record_key(record: dict)`
- L39 `_truthy(value: object)`
- L43 `_focused_path(record: dict)`
- L65 `_augment_records(records: list[dict], panel: pd.DataFrame)`
- L103 `_summary(records: list[dict])`
- L119 `_html_page(records_json: str, summary_json: str)`
- L143 `build_report(source: Path, r7_source: Path, runtime: Path, output: Path)`
- L168 `parse_args(argv=None)`
- L177 `main(argv=None)`

## scripts/build_shock_reversal_factor.py

[打开文件](../../scripts/build_shock_reversal_factor.py)

- L40 `_load_universe(start_date: str, end_date: str)`
- L64 `_compute_raw_factor(ts_codes: list, start_date: str, end_date: str, recompute: bool)`
- L109 `_cs_process(raw_df: pd.DataFrame)`
- L144 `_clean_factor_cache(factor_name: str, start_date: str, end_date: str)`
- L161 `_coverage_report(factor_name: str, start_date: str, end_date: str)`
- L187 `main()`

## scripts/build_t0_mechanism_quintiles.py

[打开文件](../../scripts/build_t0_mechanism_quintiles.py)

- L79 `parse_args(argv=None)`
- L92 `_json_safe(value)`
- L104 `_read_table(root: Path, name: str)`
- L112 `_load_scope(path: Path)`
- L135 `_forbid_frozen_outputs(out_root: Path)`
- L146 `_atomic_csv(path: Path, frame: pd.DataFrame, keys: list[str])`
- L157 `_atomic_json(path: Path, payload: dict)`
- L166 `_prepare_sector_inputs(runtime_dir: Path, parent: dict, sectors: list[str], calendar: np.ndarray)`
- L221 `_build_feature_ledger(events: pd.DataFrame, packed: dict)`
- L264 `_label_ledger(features: pd.DataFrame, duration: pd.DataFrame, l2: pd.DataFrame, paths: pd.DataFrame, events: pd.DataFrame)`
- L291 `_shock_source_counts(labeled: pd.DataFrame)`
- L296 `run_single(scope: dict, runtime_dir: Path, events_dir: Path, signal_dir: Path, parent: dict, out_dir: Path)`
- L399 `main(argv=None)`

## scripts/check_env.py

[打开文件](../../scripts/check_env.py)

- L37 `result(name: str, value: str, level: str='OK', detail: str='')`
- L42 `_mem_threshold(env_var: str, default_gb: float)`
- L56 `check_python_version()`
- L65 `check_core_dep(module_name: str, required: bool=True, attr: str='__version__')`
- L88 `check_cvxpy_solvers()`
- L107 `check_tushare_token()`
- L120 `check_tushare_connectivity()`
- L135 `check_memory_budget()`
- L160 `check_parquet_cache()`
- L176 `main()`

## scripts/compare_fulluniv_board_vs_r6.py

[打开文件](../../scripts/compare_fulluniv_board_vs_r6.py)

- L21 `_load_summary(root: Path)`
- L25 `_weights(root: Path, code: str)`
- L34 `_nav(root: Path, code: str)`
- L46 `_turnover(root: Path, code: str)`
- L53 `_row(summary: dict, code: str)`
- L60 `_year_excess(nav: pd.Series, bench: pd.Series)`
- L73 `main()`

## scripts/compare_sector_panic_e2_full214_reproduction_20260922.py

[打开文件](../../scripts/compare_sector_panic_e2_full214_reproduction_20260922.py)

- L13 `sha(path)`
- L18 `main()`

## scripts/diagnose_ab_classification.py

[打开文件](../../scripts/diagnose_ab_classification.py)

- L23 `load_factor_data(years=range(2017, 2025))`
- L41 `load_fwd_returns(start=20170224, end=20250101)`
- L76 `compute_momentum_features(prices_df)`
- L114 `load_prices_for_signal_dates(signal_dates, lookback_days=100)`
- L160 `compute_filters(mom_features)`
- L178 `main()`

## scripts/diagnose_ab_followup.py

[打开文件](../../scripts/diagnose_ab_followup.py)

- L15 `load_all_data()`
- L113 `main()`

## scripts/diagnose_factor_alignment_coverage.py

[打开文件](../../scripts/diagnose_factor_alignment_coverage.py)

- L40 `_nunique_dates(table_dir: Path, date_col: str='trade_date')`
- L70 `_factor_stats(name: str)`
- L75 `_add_calendar_days(yyyymmdd: int, days: int)`
- L80 `_simulate_lag(n_obs_dates: int, lag_days: int)`
- L95 `main()`

## scripts/diagnose_factor_duplicates.py

[打开文件](../../scripts/diagnose_factor_duplicates.py)

- L35 `_load_factor_cache(factor_name: str, start: str, end: str)`
- L92 `_classify_duplicates(df: pd.DataFrame)`
- L175 `_analyze_factor(factor_name: str, start: str, end: str)`
- L238 `main()`

## scripts/diagnose_photoresist_panic_attribution.py

[打开文件](../../scripts/diagnose_photoresist_panic_attribution.py)

- L30 `parse_args()`
- L43 `select_non_overlapping(events: pd.DataFrame, horizon: int)`
- L60 `add_backward_features(frame: pd.DataFrame, core_basket: pd.DataFrame, index_prices: pd.DataFrame, semi_code: str='931865.CSI')`
- L79 `summarize_event_returns(events: pd.DataFrame, gate_id: str, cost_bps: int)`
- L104 `summarize_by_regime(events: pd.DataFrame, gate_id: str, cost_bps: int)`
- L125 `build_coverage_diagnostics(events: pd.DataFrame, gate_id: str)`
- L137 `_distance(pool: pd.DataFrame, event: pd.Series)`
- L148 `run_strict_placebo(real: pd.DataFrame, candidates: pd.DataFrame, calendar: np.ndarray, gate_id: str, runs: int, seed: int)`
- L217 `generate_report(summary: pd.DataFrame, regime_summary: pd.DataFrame, placebo: pd.DataFrame, coverage: pd.DataFrame)`
- L240 `main()`

## scripts/diagnose_sector_panic_p1_losses.py

[打开文件](../../scripts/diagnose_sector_panic_p1_losses.py)

- L83 `sha256_file(path: Path)`
- L91 `resolve(root: Path, value: str)`
- L96 `cell(value)`
- L111 `write_csv(path: Path, rows: list[dict], columns: list[str])`
- L119 `write_json(path: Path, payload)`
- L126 `frame_rows(frame: pd.DataFrame)`
- L132 `load_prices(path: Path, codes: set[str], start: int, end: int)`
- L154 `load_calendar(path: Path)`
- L160 `load_suspend(path: Path, codes: set[str], start: int, end: int)`
- L168 `price_mismatches(fills: list[dict], prices: dict)`
- L189 `traded_span(fills: list[dict], candidates: list[dict])`
- L207 `_implementation_binding(config_path: Path)`
- L224 `failure_payload(errors: list[dict], fingerprints: dict)`
- L238 `main(argv: list[str] | None=None)`
- L328 `_calculate(config, paths, fingerprints, manifest, pre, out, candidates, orders, fills, terminals, days_sorted, attribution, fee_entry, fee_exit, calendar, suspend, prices, mismatches, end_day, end_flat, certified, specs, review_binding, config_path)`

## scripts/diagnose_v10_action_value_r1_failure.py

[打开文件](../../scripts/diagnose_v10_action_value_r1_failure.py)

- L14 `main()`

## scripts/evaluate_factor_style_signals.py

[打开文件](../../scripts/evaluate_factor_style_signals.py)

- L94 `_get_calendar()`
- L109 `_load_factor_cache(factor_name: str)`
- L166 `_load_fwd_returns()`
- L203 `_filter_by_date_range(df: pd.DataFrame, start: int, end: int, date_col: str='trade_date')`
- L216 `_rank_ic(factor_vals: pd.Series, fwd_rets: pd.Series)`
- L227 `_compute_daily_ic(factor_df: pd.DataFrame, fwd_df: pd.DataFrame, horizon: str='fwd_ret_20d')`
- L253 `_map_ic_to_available_date(daily_ic: pd.DataFrame, cal, horizon_days: int)`
- L281 `_add_calendar_days_fallback(date_int: int, days: int)`
- L290 `_compute_trailing_ic_on_available_axis(daily_ic_mapped: pd.DataFrame, lookback: int)`
- L332 `_align_trailing_to_signal_dates(trailing_df: pd.DataFrame, signal_dates: np.ndarray)`
- L385 `_compute_coverage(factor_df: pd.DataFrame, fwd_df: pd.DataFrame)`
- L424 `_evaluate_coverage(coverage_df: pd.DataFrame)`
- L469 `_dedup_momentum_factors(factor_daily_ics: Dict[str, pd.DataFrame], coverage_info: Optional[Dict[str, Dict[str, Any]]]=None)`
- L556 `_classify_style_signals(momentum_aligned: pd.DataFrame, value_aligned: pd.DataFrame, growth_aligned: pd.DataFrame, threshold: float=TRAILING_IC_THRESHOLD, mixed_margin: float=MIXED_MARGIN, growth_coverage_blocked: bool=False)`
- L652 `_validate_style_signals(style_df: pd.DataFrame, factor_daily_ics: Dict[str, pd.DataFrame], factor_data: Dict[str, pd.DataFrame], fwd_df: pd.DataFrame, horizon_col: str, momentum_rep: Optional[str], value_rep: Optional[str], growth_rep: Optional[str], growth_coverage_blocked: bool=False)`
- L861 `_compute_ic_autocorrelation(daily_ic: pd.DataFrame, max_lag: int=60)`
- L924 `_ic_autocorrelation_summary(ac_df: pd.DataFrame, factor_name: str)`
- L975 `_compute_trailing_ic_forward_relation(aligned_trailing: pd.DataFrame, daily_ic: pd.DataFrame, horizon: int=20)`
- L1095 `_write_report(out_dir: Path, validation: dict, style_df: pd.DataFrame, mom_rep: Optional[str], val_rep: Optional[str], grw_rep: Optional[str], mom_dropped: List[str], coverage_blocked: Optional[bool], corr_matrix: Optional[pd.DataFrame], args, selection_reasons: Optional[Dict]=None, ic_autocorr_summaries: Optional[Dict]=None, trail_fwd_results: Optional[Dict]=None)`
- L1327 `_write_manifest(out_dir: Path, manifest_data: Dict[str, Any])`
- L1340 `main()`

## scripts/evaluate_panic_ab_classification.py

[打开文件](../../scripts/evaluate_panic_ab_classification.py)

- L67 `load_prices()`
- L127 `load_factor(factor_name)`
- L149 `load_lag1_returns()`
- L166 `compute_forward_metrics(prices)`
- L374 `build_exec_date_map(prices)`
- L392 `classify_long(row, retention_threshold)`
- L432 `classify_short(row, retention_threshold)`
- L472 `apply_labels(merged, direction, retention_threshold)`
- L541 `classify_drop_routes(df)`
- L591 `compute_route_summary(df, retention_threshold)`
- L662 `evaluate_actions(labeled_df, direction, retention_threshold)`
- L755 `compute_quality_diagnostics(labeled_df, direction, retention_threshold)`
- L811 `compute_label_summary(labeled_df, direction, retention_threshold)`
- L865 `compute_by_year_summary(labeled_df, direction, retention_threshold)`
- L901 `generate_report(all_summaries, all_actions, all_quality, all_by_year, all_route_summaries=None, all_filter_summaries=None)`
- L1019 `main()`

## scripts/evaluate_panic_incremental_value.py

[打开文件](../../scripts/evaluate_panic_incremental_value.py)

- L33 `load_factor(fname)`
- L68 `load_fwd()`
- L76 `compute_ic(merged, value_col='value')`
- L90 `event_net_spread(merged, direction, sig_type)`

## scripts/evaluate_panic_reversal_diagnostics.py

[打开文件](../../scripts/evaluate_panic_reversal_diagnostics.py)

- L47 `load_factor(fname)`
- L89 `load_exec_lag1_returns()`
- L135 `load_daily_basic()`
- L162 `load_features(signal_dates)`
- L202 `compute_ic_metrics(merged, value_col='value')`
- L216 `compute_event_metrics(merged, direction='drop', signal_type='bin')`
- L256 `compute_rank_metrics(merged)`
- L279 `event_by_year(merged, direction, signal_type)`
- L294 `sparsity_stats(merged)`
- L313 `_compute_corr_scope(m, scope_label)`
- L347 `redundancy_check(all_factors, fwd)`
- L436 `cost_liquidity_analysis(merged, daily_basic, direction, signal_type)`
- L564 `regime_diagnostic(merged, direction, signal_type)`
- L595 `p0_screen(summary_df)`
- L650 `main()`

## scripts/evaluate_photoresist_panic_path_rules.py

[打开文件](../../scripts/evaluate_photoresist_panic_path_rules.py)

- L92 `_json_default(obj)`
- L153 `class EventRecord`
- L168 `class ExecutionContext`
- L178 `class PathResult`
- L245 `PathResult.__post_init__(self)`
- L250 `PathResult.columns()`
- L257 `class RuleTrade`
- L274 `RuleTrade.__post_init__(self)`
- L279 `RuleTrade.columns()`
- L294 `parse_args()`
- L322 `_validate_upstream_manifest(manifest_path: Path, strict: bool)`
- L409 `load_inputs(input_dir: Path)`
- L425 `_count_feature_unavailable(volume_features_list: list)`
- L434 `_dataframe_sha256(frame: pd.DataFrame | None)`
- L453 `_entry_resolution_digest(prices: pd.DataFrame, codes: list[str], signal_date: int, entry_date: int, limit_status: pd.DataFrame | None, suspend_status: pd.DataFrame | None, stock_status: pd.DataFrame | None, namechange: pd.DataFrame | None=None)`
- L502 `detect_first_triggers(core_basket: pd.DataFrame, calendar: np.ndarray, max_gap: int=MAX_CLUSTER_GAP_TRADING_DAYS)`
- L545 `compute_market_regime(index_prices: pd.DataFrame, calendar: np.ndarray, ma_window: int=REGIME_MA_WINDOW, ret_window: int=REGIME_RETURN_WINDOW, primary_code: str=REGIME_PRIMARY_INDEX)`
- L580 `get_core_codes(universe_df: pd.DataFrame, trade_date: int)`
- L591 `resolve_entry_basket(prices: pd.DataFrame, core_codes: list[str], signal_date: int, entry_date: int, calendar: np.ndarray, limit_status: pd.DataFrame | None=None, suspend_status: pd.DataFrame | None=None, namechange: pd.DataFrame | None=None, stock_status: pd.DataFrame | None=None, min_components: int=MIN_ENTRY_COMPONENTS)`
- L688 `construct_events(core_basket: pd.DataFrame, universe_df: pd.DataFrame, prices: pd.DataFrame, index_prices: pd.DataFrame, calendar: np.ndarray, start: int, end: int, limit_status: pd.DataFrame | None=None, suspend_status: pd.DataFrame | None=None, stock_status: pd.DataFrame | None=None, namechange: pd.DataFrame | None=None)`
- L781 `build_frozen_basket_path(prices: pd.DataFrame, entry_component_codes: list[str], signal_date: int, entry_date: int, calendar: np.ndarray, horizon: int, suspend_status: pd.DataFrame | None=None)`
- L866 `compute_signal_anchors(prices: pd.DataFrame, entry_component_codes: list[str], signal_date: int, entry_date: int)`
- L910 `build_semi_nav_map(path_dates: np.ndarray, index_prices: pd.DataFrame)`
- L945 `parse_event_path(basket_rets: np.ndarray, path_dates: np.ndarray, semi_nav_map: dict[int, float], signal_date: int, entry_date: int, signal_basket_return: float, signal_basket_low_return: float, next_event_date: int | None=None, observation_horizon: int=60, target_gain: float=0.05, cost_bps: int=100)`
- L1154 `_classify_path_type(path: PathResult, target_gain: float=0.05)`
- L1181 `_fill_endpoint_metrics_available(result: PathResult, rets: np.ndarray, dates: np.ndarray, semi_nav_map: dict[int, float], cost_bps: int, target_gain: float=TARGET_NET_GAIN)`
- L1193 `_fill_endpoint_metrics(result: PathResult, rets: np.ndarray, dates: np.ndarray, semi_nav_map: dict[int, float], cost_bps: int, target_gain: float=TARGET_NET_GAIN)`
- L1233 `_is_right_censored(all_dates: np.ndarray, entry_date: int, min_days: int)`
- L1242 `_nav_at_path(rets: np.ndarray, dates: np.ndarray, target_date: int)`
- L1250 `_check_basket_execution(context: ExecutionContext | None, trade_date: int, side: str)`
- L1315 `_proxy_limit_pct(code: str, trade_date: int, stock_name: str | None=None)`
- L1346 `_try_exit_or_defer(exit_date: int, context: ExecutionContext | None, calendar: np.ndarray, trunc_date: int | None=None, max_defer_days: int=3)`
- L1399 `_round_trip_cost(weight: float, cost_bps: int)`
- L1408 `_holding_has_gap(rets: np.ndarray, dates: np.ndarray, entry_date: int, exit_date: int)`
- L1422 `_position_return(event_ret: float, entry_event_ret: float)`
- L1431 `_stop_scan_position(rets: np.ndarray, dates: np.ndarray, calendar: np.ndarray, entry_date: int, entry_event_ret: float, hold_days: int, stop_levels: list[float], trunc_date: int | None=None)`
- L1478 `simulate_rule_r0(signal_id: str, event_date: int, entry_date: int, rets: np.ndarray, dates: np.ndarray, calendar: np.ndarray, cost_bps: int=100, hold_days: int=20, stop_levels: list[float] | None=None, trunc_date: int | None=None, execution_context: ExecutionContext | None=None, path_result: PathResult | None=None)`
- L1604 `simulate_rule_r1(signal_id: str, event_date: int, entry_date_original: int, path: PathResult, rets: np.ndarray, dates: np.ndarray, calendar: np.ndarray, cost_bps: int=100, hold_days: int=20, stop_levels: list[float] | None=None, trunc_date: int | None=None, execution_context: ExecutionContext | None=None)`
- L1755 `simulate_rule_r2(signal_id: str, event_date: int, entry_date: int, path: PathResult, rets: np.ndarray, dates: np.ndarray, calendar: np.ndarray, cost_bps: int=100, hold_days: int=20, stop_levels: list[float] | None=None, trunc_date: int | None=None, execution_context: ExecutionContext | None=None)`
- L1948 `simulate_rule_r3(signal_id: str, event_date: int, entry_date: int, path: PathResult, rets: np.ndarray, dates: np.ndarray, calendar: np.ndarray, cost_bps: int=100, hold_days: int=20, stop_levels: list[float] | None=None, trunc_date: int | None=None, execution_context: ExecutionContext | None=None)`
- L2248 `_flatten_trade(trade: RuleTrade)`
- L2277 `compute_paired_differences(trade_ledger: pd.DataFrame, primary_cost: int=100)`
- L2320 `bootstrap_ci(values: np.ndarray, n_bootstrap: int=2000, ci_level: float=0.95, seed: int=20260710)`
- L2335 `cluster_bootstrap_ci(values: np.ndarray, cluster_ids: np.ndarray, n_bootstrap: int=2000, ci_level: float=0.95, seed: int=20260710)`
- L2377 `build_portfolio_curve(trade_ledger: pd.DataFrame, calendar: np.ndarray, basket_paths: dict[str, tuple[np.ndarray, np.ndarray]], rule_id: str='R0', cost_bps: int=100, initial_capital: float=1.0, full_period_start: int | None=None, full_period_end: int | None=None)`
- L2650 `generate_report(path_ledger: pd.DataFrame, trade_ledger: pd.DataFrame, paired: pd.DataFrame, events: list, start: int, end: int, primary_cost: int=100, cost_scenarios: list[int] | None=None, bootstrap_runs: int=2000, bootstrap_ci_level: float=0.95, seed: int=20260710, config_hash: str='', calendar: np.ndarray | None=None, portfolio_metrics: dict[str, dict] | None=None, **kwargs)`
- L3094 `_frozen_run_config(args)`
- L3145 `_frozen_strategy_config(args)`
- L3157 `_stable_json_sha256(payload: dict)`
- L3164 `_apply_amount_ratio_candidate(baseline_return: float, feature_value: float | None, threshold: float)`
- L3176 `_forward_start_after_freeze(frozen_at: str)`
- L3217 `_build_shadow_contract(args, upstream_manifest: dict | None=None, frozen_at: str | None=None)`
- L3253 `_validate_shadow_contract(contract: dict, args)`
- L3307 `_canonical_shadow_row(row: pd.Series)`
- L3343 `append_shadow_outcomes(current_ledger: pd.DataFrame, existing_path: Path | None, forward_start: int)`
- L3448 `_portfolio_metrics_manifest(metrics: dict[str, dict])`
- L3468 `_build_manifest(args, path_ledger, events, config_hash: str, input_digests: dict[str, str] | None=None, path_failures: list[dict] | None=None, tradability_audit: dict | None=None, upstream_manifest: dict | None=None, portfolio_metrics: dict[str, dict] | None=None, shadow_contract: dict | None=None)`
- L3625 `_validate_tradability_coverage(events: list, limit_status: pd.DataFrame | None, suspend_status: pd.DataFrame | None, stock_status: pd.DataFrame | None, suspend_coverage_proven: bool=False)`
- L3730 `_main_impl(args: argparse.Namespace)`
- L4830 `class _EvaluationRunLock`
- L4833 `_EvaluationRunLock.__init__(self, output_dir: Path)`
- L4837 `_EvaluationRunLock.__enter__(self)`
- L4873 `_EvaluationRunLock.__exit__(self, exc_type, exc, traceback)`
- L4884 `main()`

## scripts/evaluate_photoresist_panic_reversal.py

[打开文件](../../scripts/evaluate_photoresist_panic_reversal.py)

- L57 `parse_args()`
- L68 `load_yaml(path: Path)`
- L73 `collect_feature_status(research_config: dict)`
- L122 `_normalize(df: pd.DataFrame)`
- L133 `_iter_year_dirs(base: Path, start: int, end: int)`
- L146 `build_trading_calendar_from_prices(start: int, end: int)`
- L158 `build_calendar_index(calendar: np.ndarray)`
- L162 `trading_day_offset(calendar: np.ndarray, date: int, offset: int)`
- L175 `compute_listing_age(prices: pd.DataFrame, calendar: np.ndarray)`
- L182 `compute_amount_20d_avg(prices: pd.DataFrame)`
- L192 `check_consecutive_limit_down(ts_code: str, trade_date: int, limit_status: pd.DataFrame | None, prices: pd.DataFrame, n_days: int=2)`
- L213 `is_suspended(ts_code: str, trade_date: int, suspend_status: pd.DataFrame | None, prices: pd.DataFrame)`
- L238 `compute_forward_returns(events_df: pd.DataFrame, prices: pd.DataFrame, core_basket: pd.DataFrame, index_prices: pd.DataFrame, calendar: np.ndarray)`
- L339 `_get_available_stocks_v2(event_date: int, exec_date: int, universe_df: pd.DataFrame, prices: pd.DataFrame, calendar: np.ndarray, listing_age_map: pd.Series, amt_20d_map: pd.Series, limit_status: pd.DataFrame | None, suspend_status: pd.DataFrame | None, stock_status_raw: pd.DataFrame | None, eligibility: dict)`
- L409 `_select_top1_stock(available: pd.DataFrame, rule_name: str, rule_cfg: dict, event_date: int, core_basket: pd.DataFrame, prices: pd.DataFrame, exec_date: int, amt_20d_map: pd.Series)`
- L461 `_simulate_trade_close(ts_code: str, exec_date: int, hold_days: int, prices: pd.DataFrame, calendar: np.ndarray, cost: float, suspend_status: pd.DataFrame | None)`
- L559 `evaluate_top1_rules(events_df: pd.DataFrame, prices: pd.DataFrame, core_basket: pd.DataFrame, universe_df: pd.DataFrame, calendar: np.ndarray, top1_config: dict, cost_bps: int=20, limit_status: pd.DataFrame | None=None, suspend_status: pd.DataFrame | None=None, stock_status: pd.DataFrame | None=None, eligibility: dict | None=None)`
- L645 `compute_basket_contribution(fwd_returns: pd.DataFrame, events_df: pd.DataFrame, prices: pd.DataFrame, core_basket: pd.DataFrame, universe_df: pd.DataFrame, calendar: np.ndarray)`
- L724 `compute_basket_leave_one_out(fwd_returns: pd.DataFrame, events_df: pd.DataFrame, prices: pd.DataFrame, core_basket: pd.DataFrame, universe_df: pd.DataFrame, calendar: np.ndarray)`
- L816 `compute_concentration_diagnostics(trades_df: pd.DataFrame)`
- L841 `compute_leave_one_out(trades_df: pd.DataFrame)`
- L878 `compute_robustness(fwd_returns: pd.DataFrame, trades_df: pd.DataFrame, research_config: dict)`
- L920 `evaluate_go_nogo(fwd_returns: pd.DataFrame, trades_df: pd.DataFrame, concentration: pd.DataFrame, top1_loo: pd.DataFrame, basket_loo: pd.DataFrame, robustness: pd.DataFrame, go_nogo_config: dict, not_implemented_features: list[str] | None=None)`
- L1073 `generate_report(fwd_returns, trades_df, concentration, top1_loo, basket_loo, robustness, go_nogo_result, events_df, out_dir, not_implemented_features, limit_status_src, suspend_status_src, implemented_features: list[str] | None=None)`
- L1174 `main()`

## scripts/evaluate_photoresist_shadow_gates.py

[打开文件](../../scripts/evaluate_photoresist_shadow_gates.py)

- L51 `_json_default(value)`
- L63 `stable_sha256(payload)`
- L71 `validate_gate_contract(contract: dict)`
- L126 `class Gate`
- L133 `Gate.as_dict(self)`
- L143 `_gate(name: str, passed: bool, value, threshold, detail: str)`
- L147 `_bootstrap_mean_ci(values: np.ndarray, runs: int, confidence: float, seed: int, cluster_ids: np.ndarray | None=None)`
- L202 `_top3_profit_share(values: np.ndarray)`
- L210 `_leave_one_out_all_positive(values: np.ndarray)`
- L218 `_rule_rows(outcomes: pd.DataFrame, rule_id: str, criteria: dict)`
- L230 `_summary(rows: pd.DataFrame)`
- L241 `evaluate_shadow_gates(outcomes: pd.DataFrame, portfolio_metrics: dict, gate_contract: dict)`
- L443 `validate_data_freshness(upstream_manifest: dict, gate_contract: dict)`
- L580 `_pre_registration_summary(shadow_dir: Path, primary_cost_bps: int=100)`
- L639 `validate_shadow_artifacts(shadow_dir: Path, research_contract: dict, manifest: dict, upstream_manifest: dict, gate_contract: dict, outcomes: pd.DataFrame, current_ledger: pd.DataFrame)`
- L1089 `render_report(result: dict, gate_contract: dict)`
- L1144 `parse_args()`
- L1152 `main()`

## scripts/evaluate_regime_predictiveness.py

[打开文件](../../scripts/evaluate_regime_predictiveness.py)

- L48 `class RunArtifact`
- L55 `_pct(x: Any, digits: int=1)`
- L61 `_num(x: Any, digits: int=4)`
- L67 `_parse_annual_year(run_name: str)`
- L79 `discover_run_artifacts(runs_root: Path, start_year: int, end_year: int, run_id_contains: str | None=None)`
- L121 `load_prediction_panel(artifacts: list[RunArtifact])`
- L167 `add_expost_labels(panel: pd.DataFrame)`
- L193 `compute_outputs(panel: pd.DataFrame)`
- L320 `classify_status(accuracy_comparable: float, return_spread: float, range_bound_share: float, high_vol_abs_lift: float)`
- L344 `write_report(out_dir: Path, panel: pd.DataFrame, thresholds: dict[str, float], outputs: dict[str, Any], artifacts: list[RunArtifact], run_id_contains: str | None)`
- L399 `build_markdown_report(summary: dict[str, Any], thresholds: dict[str, float], outputs: dict[str, Any], artifacts: list[RunArtifact])`
- L464 `parse_args()`
- L484 `main()`

## scripts/evaluate_sector_panic_p1_minimal_20260924.py

[打开文件](../../scripts/evaluate_sector_panic_p1_minimal_20260924.py)

- L16 `sha(path)`
- L24 `main()`

## scripts/evaluate_sector_structural_feasibility.py

[打开文件](../../scripts/evaluate_sector_structural_feasibility.py)

- L58 `parse_args(argv: list[str] | None=None)`
- L70 `_read_table(root: Path, name: str)`
- L78 `_atomic_write_json(path: Path, payload: dict)`
- L96 `_atomic_write_csv(path: Path, frame: pd.DataFrame)`
- L113 `_load_scope(path: Path)`
- L125 `_capture_summary(capture: pd.DataFrame)`
- L157 `_blocked_entry_capture_summary(capture: pd.DataFrame)`
- L190 `_episode_robustness(events: pd.DataFrame, capture: pd.DataFrame)`
- L236 `_positive_episode_concentration(robustness: pd.DataFrame)`
- L249 `_stop_summary(stop: pd.DataFrame)`
- L291 `_regime_summary(events: pd.DataFrame, capture: pd.DataFrame)`
- L319 `run(scope_path: Path, runtime_dir: Path, out_dir: Path, sectors: list[str] | None)`
- L735 `main(argv: list[str] | None=None)`

## scripts/evaluate_three_state_gate.py

[打开文件](../../scripts/evaluate_three_state_gate.py)

- L96 `load_prices(start: str, end: str)`
- L129 `load_factor(fname: str)`
- L149 `list_all_factors()`
- L163 `evaluate_factor(fname: str, prices_val: pd.DataFrame, prices_cal: pd.DataFrame)`
- L346 `main()`

## scripts/explore_market_state_vs_factor_ic.py

[打开文件](../../scripts/explore_market_state_vs_factor_ic.py)

- L80 `_load_factor_cache(factor_name: str)`
- L135 `_load_fwd_returns()`
- L168 `_load_index_daily(index_code: str, start: str, end: str)`
- L184 `_load_index_cache_fast(index_code: str)`
- L213 `_rank_ic(factor_vals: pd.Series, fwd_rets: pd.Series, min_obs: int=30)`
- L225 `_compute_factor_ic_series(factor_df: pd.DataFrame, fwd_df: pd.DataFrame, horizon: str='fwd_ret_20d')`
- L249 `_compute_index_spread(idx1: pd.DataFrame, idx2: pd.DataFrame, window: int=20, label: str='spread')`
- L281 `_build_regime_features(index_df: pd.DataFrame, prices_df: Optional[pd.DataFrame], signal_dates: np.ndarray)`
- L313 `_build_simplified_features(index_df: pd.DataFrame, signal_dates: np.ndarray)`
- L376 `_conditional_ic_analysis(panel: pd.DataFrame, state_col: str, factor_name: str, n_quantiles: int=4)`
- L485 `_apply_fdr_correction(all_results: List[Dict[str, Any]], raw_p_threshold: float=0.05, fdr_q_threshold: float=0.1, min_abs_ic_spread: float=0.02)`
- L571 `_classify_findings_into_tiers(all_results: List[Dict[str, Any]], coverage_blocked_factors: set)`
- L644 `_build_rule_interpretation(result: Dict[str, Any])`
- L688 `_compute_factor_coverage_for_market_state(factor_df: pd.DataFrame, fwd_df: pd.DataFrame)`
- L711 `main()`
- L1170 `_write_tiered_report(out_dir: Path, tiers: Dict[str, List[Dict[str, Any]]], all_results: List[Dict[str, Any]], factor_coverage: Dict[str, Dict[str, Any]], coverage_blocked_factors: set, args, n_signal_dates: int, n_with_all: int)`

## scripts/factor_quality_rebuild.py

[打开文件](../../scripts/factor_quality_rebuild.py)

- L57 `timed_stage(name: str)`
- L72 `_pct(value: Any, digits: int=1)`
- L78 `_num(value: Any, digits: int=3)`
- L84 `_rank_ic(factor_vals: pd.Series, fwd_rets: pd.Series)`
- L95 `_pearson_ic(factor_vals: pd.Series, fwd_rets: pd.Series)`
- L105 `_add_calendar_days(date_int: int, days: int)`
- L112 `_get_trading_calendar()`
- L123 `_config_checksum(config_path: Path)`
- L131 `_validate_factor_config(factor_cfg: dict)`
- L185 `class RunDiagnostics`
- L191 `RunDiagnostics.__init__(self, diag_dir: Path, run_id: str, config_path: str, config_sha256: str, seed: int, factor_count: int, out_dir: str, out_doc: str)`
- L219 `RunDiagnostics._write_manifest(self, status: str, end_time: str='')`
- L236 `RunDiagnostics.mark_success(self)`
- L239 `RunDiagnostics.mark_failed(self)`
- L242 `RunDiagnostics.log_progress(self, factor: str, factor_index: int, stage: str, status: str, elapsed_sec: float, raw_rows: int=0, aligned_rows: int=0, message: str='')`
- L259 `RunDiagnostics.log_stage_timing(self, stage: str, elapsed_sec: float, status: str='OK', rows_out: int=0, warning: str='')`
- L272 `RunDiagnostics.log_error(self, stage: str, factor: str, error_type: str, error_message: str, traceback_str: str='')`
- L285 `_write_csv_safe_append(path: Path, rows: list[dict], columns: list[str])`
- L322 `_validate_robustness_config(robustness_cfg: dict)`
- L350 `_write_csv_safe(out_path: Path, rows: list[dict], columns: list[str])`
- L369 `_write_partial_csvs(partial_dir: Path, input_audits: list[dict], direction_audits: list[dict], alignment_audits: list[dict], ic_rows_all: list[dict], quantile_rows_all: list[dict], turnover_cost_all: list[dict], neutralization_diags: list[dict], ic_trends: list[dict])`
- L430 `_publish_outputs(out_dir: Path, run_dir: Path, out_doc: Path)`
- L474 `_load_factor_cache_raw(factor_name: str, start: str, end: str)`
- L548 `_clean_factor_panel(raw_df: pd.DataFrame)`
- L570 `_load_fwd_returns(start: str, end: str)`
- L609 `_load_daily_basic(start: str, end: str)`
- L659 `_audit_factor_input(factor_cfg: dict, raw_df: pd.DataFrame, fwd: pd.DataFrame, window_start: str, window_end: str)`
- L802 `_build_aligned_panel(factor_cfg: dict, clean_df: pd.DataFrame, fwd: pd.DataFrame, horizon: str, cal_start: str, cal_end: str, val_start: str, val_end: str, watch_start: str, watch_end: str)`
- L1018 `_neutralize_by_mcap(factor_name: str, aligned_panel: pd.DataFrame, log_market_cap_panel: pd.DataFrame, min_coverage_pct: float=70.0)`
- L1158 `_audit_factor_direction(factor_cfg: dict, aligned_panel: pd.DataFrame, cal_start: str, cal_end: str, value_col: str='value_raw')`
- L1230 `_compute_ic_by_year(factor_cfg: dict, aligned_panel: pd.DataFrame, direction_info: dict, years: list[int], value_col: str, basis: str)`
- L1292 `_compute_quantile_portfolios(factor_cfg: dict, aligned_panel: pd.DataFrame, direction_info: dict, value_col: str, weighting: str='equal_weight', daily_basic: Optional[pd.DataFrame]=None)`
- L1368 `_compute_real_turnover_cost(factor_cfg: dict, portfolios: list[dict], fwd: pd.DataFrame, aligned_panel: pd.DataFrame, direction_info: dict, years: list[int], value_col: str, basis: str, weighting: str, cost_bps: float)`
- L1553 `_compute_quantile_returns(factor_cfg: dict, aligned_panel: pd.DataFrame, direction_info: dict, years: list[int], value_col: str, basis: str, cost_bps: float, turnover_rows: Optional[list[dict]]=None)`
- L1644 `_compute_ic_trend(factor_name: str, aligned_panel: pd.DataFrame, direction_info: dict, value_col: str, basis: str, val_start: str, val_end: str, p_value_threshold: float=0.1)`
- L1705 `_compute_rolling_window_gate(factor_cfg: dict, ic_rows_all: list[dict], quantile_rows_all: list[dict], direction_info: dict, rolling_windows: list[dict], gate_cfg: dict)`
- L1781 `_market_cap_cny(series: pd.Series, capacity_cfg: dict)`
- L1791 `_daily_basic_amount_cny(db_date: pd.DataFrame, capacity_cfg: dict)`
- L1815 `_convert_amount_to_cny(series: pd.Series, amount_unit: str)`
- L1826 `_compute_capacity_audit(factor_cfg: dict, aligned_panel: pd.DataFrame, direction_info: dict, value_col: str, basis: str, daily_basic: pd.DataFrame, years: list[int], capacity_cfg: dict, weighting: str='equal_weight', daily_basic_by_date: Optional[dict]=None)`
- L1985 `_compute_regime_breakdown(factor_cfg: dict, aligned_panel: pd.DataFrame, direction_info: dict, value_col: str, basis: str, years: list[int])`
- L2096 `_compute_neutralization_diagnostic(factor_cfg: dict, ic_raw: list[dict], ic_neutral: list[dict], quant_raw: list[dict], quant_neutral: list[dict], val_years: list[int], neut_meta: Optional[dict]=None, neutralization_cfg: Optional[dict]=None)`
- L2198 `_compute_correlation_clusters(factor_dfs: dict[str, pd.DataFrame], fwd: pd.DataFrame, direction_infos: dict[str, dict], factor_cfgs: list[dict], gate_results: list[dict], threshold: float=0.85)`
- L2324 `_apply_quality_gate(factor_cfg: dict, input_audit: dict, alignment_audit: dict, direction_info: dict, ic_raw: list[dict], ic_neutral: list[dict], quant_raw: list[dict], quant_neutral: list[dict], turnover_cost_rows: list[dict], ic_trend: dict, rolling_results: list[dict], capacity_rows: list[dict], gate_cfg: dict, gate_basis_cfg: dict, robustness_cfg: dict, capacity_cfg: dict, neutralization_diag: Optional[dict]=None, neutralization_cfg: Optional[dict]=None)`
- L2579 `_generate_candidate_pool(gate_results: list[dict], factor_cfgs: list[dict], correlation_clusters: pd.DataFrame, out_path: Path)`
- L2654 `_write_report(out_doc: Path, input_audits: list[dict], direction_audits: list[dict], alignment_audits: list[dict], ic_rows_all: list[dict], quantile_rows_all: list[dict], turnover_cost_all: list[dict], neutralization_diags: list[dict], ic_trends: list[dict], rolling_gates: list[dict], correlation_clusters: pd.DataFrame, capacity_audits: list[dict], regime_breakdowns: list[dict], gate_results: list[dict], pool: dict, config_path: str='', config_sha256: str='', seed: int=42)`
- L2917 `main()`

## scripts/fast_vs_phase2_attribution.py

[打开文件](../../scripts/fast_vs_phase2_attribution.py)

- L31 `_pct(value: Any, digits: int=1)`
- L37 `_num(value: Any, digits: int=2)`
- L43 `_compound(series: pd.Series)`
- L50 `_annualized_return(period_returns: pd.Series)`
- L57 `_information_ratio(returns: pd.Series)`
- L67 `_max_drawdown(period_returns: pd.Series)`
- L76 `_parse_weights(value: Any)`
- L99 `_read_year_partitions(dataset: str, years: set[int], columns: list[str])`
- L110 `_next_trade_date(trade_dates: list[int], date: int)`
- L117 `_load_phase2_run(runs_csv: Path, case: str | None)`
- L127 `_build_or_load_composite(cfg_path: Path, start: str, end: str, out_dir: Path, force_rebuild: bool)`
- L195 `_load_price_matrix(dates: set[int])`
- L206 `_load_index_returns(periods: pd.DataFrame)`
- L232 `_build_fast_holdings(composite: pd.DataFrame, start: str, end: str, top_n: int)`
- L316 `_load_phase2_periods(run_dir: Path)`
- L335 `_load_phase2_holdings(run_dir: Path, periods: pd.DataFrame)`
- L356 `_build_rank_panel(composite: pd.DataFrame)`
- L366 `_stock_return_lookup(periods: pd.DataFrame)`
- L390 `_compare_holdings(fast_periods: pd.DataFrame, fast_holdings: pd.DataFrame, phase2_periods: pd.DataFrame, phase2_holdings: pd.DataFrame, rank_panel: pd.DataFrame)`
- L509 `_weighted_average(df: pd.DataFrame, value_col: str, weight_col: str)`
- L518 `_subset_mean_return(df: pd.DataFrame, names: set[str])`
- L525 `_subset_contribution(df: pd.DataFrame, names: set[str], weight_col: str)`
- L534 `_monthly_summary(period_compare: pd.DataFrame)`
- L558 `_metrics_from_periods(period_compare: pd.DataFrame)`
- L588 `_write_report(out_doc: Path, row: pd.Series, composite_diag: dict[str, Any], metrics: dict[str, float], period_compare: pd.DataFrame, monthly: pd.DataFrame, diff: pd.DataFrame)`
- L741 `_stock_summary(df: pd.DataFrame, ascending: bool=False)`
- L756 `main()`

## scripts/fetch_index_constituent_prices.py

[打开文件](../../scripts/fetch_index_constituent_prices.py)

- L36 `is_beijing(ts_code: str)`
- L40 `load_index_weight()`
- L57 `needed_constituent_codes(iw: pd.DataFrame)`
- L62 `_unique_codes(table: str, start: int, end: int)`
- L76 `_write_merged(cache, table: str, df: pd.DataFrame, partition_cols: list[str])`
- L87 `diagnose(start: str, end: str, *, universe_start: str=UNIVERSE_START, universe_end: str=UNIVERSE_END)`
- L136 `_unique_codes_industry()`
- L147 `probe_replica_coverage(start: str, end: str)`
- L193 `run(start: str, end: str, *, dry_run: bool, out_dir: Path, universe_start: str=UNIVERSE_START, universe_end: str=UNIVERSE_END, skip_coverage: bool=False)`
- L361 `main()`

## scripts/fetch_limit_status_product_exec.py

[打开文件](../../scripts/fetch_limit_status_product_exec.py)

- L50 `_load_trade_dates(start: str, end: str)`
- L61 `_load_index_weight()`
- L70 `_load_limit_pairs(loader, start: str, end: str)`
- L80 `_month_key(date: int)`
- L84 `_fetch_full_day(client, trade_date: int)`
- L99 `_keep_limit_cols(df: pd.DataFrame)`
- L112 `_write_month(loader, chunks: list[pd.DataFrame])`
- L122 `_report_path(out_dir: Path)`
- L127 `_load_prices_preclose(start: str, end: str)`
- L146 `_load_st_periods()`
- L155 `_backfill_from_official(loader, client, required: set[tuple[str, int]], present: set[tuple[str, int]], start: str, end: str, board: str)`
- L232 `_official_history_blocked(client)`
- L245 `_backfill_from_preclose(loader, required: set[tuple[str, int]], present: set[tuple[str, int]], start: str, end: str, exec_dates: list[int], board: str=BOARD_SSE_SZSE_MAIN)`
- L290 `run(start: str, end: str, *, dry_run: bool, out_dir: Path, source: str='auto', board: str=BOARD_SSE_SZSE_MAIN)`
- L394 `main()`

## scripts/fetch_photoresist_data.py

[打开文件](../../scripts/fetch_photoresist_data.py)

- L55 `parse_args()`
- L69 `fetch_trade_calendar(client: TushareClient, start: str, end: str)`
- L84 `fetch_prices(client: TushareClient, codes: list[str], start: str, end: str)`
- L145 `fetch_adj_factor(client: TushareClient, codes: list[str], start: str, end: str)`
- L163 `build_adjusted_price_frame(raw_prices: pd.DataFrame, adj_factors: pd.DataFrame)`
- L198 `persist_adjusted_prices(client: TushareClient, raw_prices: pd.DataFrame, adj_factors: pd.DataFrame, start: str, end: str, requested_codes: list[str])`
- L259 `fetch_index_daily(client: TushareClient, codes: list[str], start: str, end: str)`
- L281 `fetch_limit_status(client: TushareClient, codes: list[str], start: str, end: str)`
- L325 `fetch_suspend_status(client: TushareClient, codes: list[str], start: str, end: str)`
- L342 `fetch_stock_status(client: TushareClient)`
- L355 `fetch_namechange(client: TushareClient, codes: list[str])`
- L370 `fetch_daily_basic(client: TushareClient, codes: list[str], start: str, end: str)`
- L388 `check_cache()`
- L472 `main()`

## scripts/fetch_sector_panic_runtime_data.py

[打开文件](../../scripts/fetch_sector_panic_runtime_data.py)

- L35 `parse_args()`
- L54 `class Fetcher`
- L55 `Fetcher.__init__(self, pro, fragment_dir: Path, calls_per_minute: int, fallback_fragment_dirs: list[Path] | None=None)`
- L74 `Fetcher._paths(self, table: str, key: str)`
- L80 `Fetcher.fetch(self, table: str, key: str, function, **kwargs)`
- L125 `_chunks(values: list[str], size: int)`
- L130 `_year_ranges(start: int, end: int)`
- L135 `_month_ranges(start: int, end: int)`
- L143 `_split_calendar_ranges(start: int, end: int, days: int=7)`
- L152 `_combine(frames: list[pd.DataFrame], keys: list[str])`
- L175 `_write_table(out_dir: Path, name: str, frame: pd.DataFrame)`
- L197 `_load_scope_contract(scope_path: Path)`
- L233 `main()`

## scripts/fetch_shenwan_l1_daily.py

[打开文件](../../scripts/fetch_shenwan_l1_daily.py)

- L24 `run(start: str, end: str, *, dry_run: bool, out_dir: Path)`
- L91 `main()`

## scripts/fix_202001.py

[打开文件](../../scripts/fix_202001.py)

无顶层函数/类；阅读模块常量、导入或入口逻辑。

## scripts/freeze_sector_panic_e2_full214_20260922.py

[打开文件](../../scripts/freeze_sector_panic_e2_full214_20260922.py)

- L14 `sha(p)`
- L18 `main()`

## scripts/frozen_backtest_attribution.py

[打开文件](../../scripts/frozen_backtest_attribution.py)

- L54 `_pct(value: Any, digits: int=1)`
- L60 `_num(value: Any, digits: int=2)`
- L66 `_compound(series: pd.Series)`
- L73 `_idxmax_label(values: pd.Series)`
- L80 `_resolve_path(path: str | Path)`
- L87 `_read_json(path: Path)`
- L91 `_parse_weights(value: Any)`
- L111 `_load_runs(path: Path)`
- L138 `_load_period_returns(row: pd.Series)`
- L156 `_filter_run_dates(df: pd.DataFrame, row: pd.Series, date_col: str='trade_date')`
- L163 `_summarise_regime_run(row: pd.Series)`
- L210 `_overlay_quality(row: pd.Series)`
- L236 `_strategy_summary(validation: pd.DataFrame)`
- L253 `_relative_excess(validation: pd.DataFrame)`
- L265 `_period_diff_tables(runs: pd.DataFrame)`
- L311 `_flatten_dict(value: Any, prefix: str='')`
- L321 `_config_diff_table(c_path: Path, d_path: Path)`
- L339 `_expand_holdings(row: pd.Series)`
- L366 `_factor_value_column(df: pd.DataFrame, factor: str)`
- L375 `_load_factor_cache(factor: str, years: set[int], ts_codes: set[str])`
- L402 `_add_factor_asof(base: pd.DataFrame, factor: str, factor_df: pd.DataFrame, max_lag_days: int)`
- L458 `_weighted_mean(group: pd.DataFrame, value_col: str)`
- L468 `_holdings_style_exposure(validation_runs: pd.DataFrame)`
- L547 `_write_report(out_doc: Path, runs: pd.DataFrame, strategy_summary: pd.DataFrame, relative: pd.DataFrame, regime_summary: pd.DataFrame, sleeve_deltas: pd.DataFrame, period_summary: pd.DataFrame, overlay_quality: pd.DataFrame, exposure_delta: pd.DataFrame, lag_summary: pd.DataFrame, config_diff: pd.DataFrame)`
- L719 `main()`

## scripts/frozen_backtest_validation.py

[打开文件](../../scripts/frozen_backtest_validation.py)

- L45 `class Strategy`
- L225 `_arg_value(args: tuple[str, ...], flag: str)`
- L234 `_norm_path_like(value: Any)`
- L240 `_run_dirs()`
- L251 `_compute_file_sha256(file_path: str)`
- L262 `_compute_factor_list_hash(factor_list: list)`
- L270 `_manifest_matches(run_dir: Path, start: str, end: str, top_n: int, strategy: Strategy, check_hashes: bool=True, allow_legacy_manifest: bool=False)`
- L360 `_periods_within_manifest_window(run_dir: Path)`
- L376 `_has_valid_phase2_metrics(run_dir: Path)`
- L392 `_find_existing_run(start: str, end: str, top_n: int, strategy: Strategy, check_hashes: bool=True, allow_legacy_manifest: bool=False)`
- L406 `_new_run_dir(before: set[Path])`
- L411 `_write_reuse_audit_log(log_path: Path, year: int, start: str, end: str, top_n: int, strategy: Strategy, existing: Path)`
- L462 `_run_one(year: int, start: str, end: str, top_n: int, strategy: Strategy, log_dir: Path, reuse_existing: bool, check_hashes: bool=True, allow_legacy_manifest: bool=False)`
- L516 `_load_metrics(run_dir: Path | None)`
- L526 `_go_nogo_overall(metrics: dict[str, Any])`
- L530 `_go_nogo_reasons(metrics: dict[str, Any])`
- L537 `_max_diagnostic_period_end(run_dir: Path | None)`
- L552 `_fmt_pct(value: Any, digits: int=1)`
- L558 `_fmt_num(value: Any, digits: int=2)`
- L564 `_write_report(df: pd.DataFrame, out_doc: Path, include_discovery_2025: bool)`
- L725 `main()`

## scripts/generate_exec_lag1_returns.py

[打开文件](../../scripts/generate_exec_lag1_returns.py)

- L28 `load_prices()`
- L52 `compute_lag_returns(prices)`
- L123 `extract_outliers(fwd_df)`
- L154 `quality_summary(fwd_df, outliers_df)`
- L193 `alignment_audit(factor_signal_dates, prices)`
- L256 `main()`

## scripts/generate_go_nogo_decision.py

[打开文件](../../scripts/generate_go_nogo_decision.py)

- L52 `_fmt_pct(value, digits=1)`
- L58 `_fmt_num(value, digits=2)`
- L64 `_to_markdown_table(frame: pd.DataFrame)`
- L82 `load_runs(csv_paths: List[Path])`
- L94 `check_completeness(df: pd.DataFrame, candidate_strategies: List[str], required_validation_years: Optional[List[int]]=None, required_ytd_years: Optional[List[int]]=None)`
- L156 `compute_summary(df: pd.DataFrame, strategy: str, sample: str='validation')`
- L188 `evaluate_thresholds(summary: Dict)`
- L199 `write_report(df: pd.DataFrame, out_path: Path, base_strategies: List[str], candidate_strategies: List[str], allow_incomplete: bool=False, required_validation_years: Optional[List[int]]=None, required_ytd_years: Optional[List[int]]=None)`
- L378 `main()`

## scripts/hard_gate_checker.py

[打开文件](../../scripts/hard_gate_checker.py)

- L38 `class GateResult`
- L47 `class HardGateResult`
- L56 `HardGateResult.is_pass(self)`
- L59 `HardGateResult.failure_summary(self)`
- L73 `_gate_diagnostic_only(candidate_name: str, trade_ledger_with: pd.DataFrame | None=None, trade_ledger_without: pd.DataFrame | None=None)`
- L99 `_gate_single_candidate(active_candidates: list[str], candidate_name: str)`
- L113 `_gate_monotonic_relationship(feature_values: np.ndarray, net_returns: np.ndarray, min_spearman_r: float=0.0, min_n: int=10)`
- L157 `_gate_multiple_testing_tally(total_tests: int, max_bonferroni: int=5)`
- L170 `_gate_threshold_from_training(threshold_source: str)`
- L179 `_gate_median_not_worse(baseline_median: float, candidate_median: float, tolerance: float=0.0)`
- L191 `_gate_left_tail_not_wider(baseline_returns: np.ndarray, candidate_returns: np.ndarray, quantile: float=0.1)`
- L211 `_gate_top3_not_dominant(baseline_returns: np.ndarray, candidate_returns: np.ndarray, max_contribution_ratio: float=0.5)`
- L244 `_gate_jackknife_stable(baseline_returns: np.ndarray, candidate_returns: np.ndarray, sign_sensitivity: float=1.0)`
- L282 `_gate_cost_100bp_improves(baseline_net_100bp: np.ndarray, candidate_net_100bp: np.ndarray)`
- L298 `_gate_year_consistency(returns_by_year: dict[int, tuple[np.ndarray, np.ndarray]], min_consistent_ratio: float=1.0)`
- L333 `_gate_viewed_once(firewall_sealed: bool)`
- L345 `class HardGateChecker`
- L348 `HardGateChecker.__init__(self, candidate_name: str, firewall_sealed: bool=False)`
- L354 `HardGateChecker.check_diagnostic_only(self, trade_ledger_with=None, trade_ledger_without=None)`
- L361 `HardGateChecker.check_single_candidate(self, active_candidates: list[str])`
- L367 `HardGateChecker.check_monotonic_relationship(self, feature_values: np.ndarray, net_returns: np.ndarray)`
- L374 `HardGateChecker.check_multiple_testing_tally(self, total_tests: int)`
- L380 `HardGateChecker.check_threshold_from_training(self, threshold_source: str)`
- L386 `HardGateChecker.check_viewed_once(self)`
- L392 `HardGateChecker.check_year_consistency(self, returns_by_year: dict[int, tuple[np.ndarray, np.ndarray]])`
- L400 `HardGateChecker.check_median_not_worse(self, baseline_median: float, candidate_median: float)`
- L407 `HardGateChecker.check_left_tail_not_wider(self, baseline_returns: np.ndarray, candidate_returns: np.ndarray)`
- L414 `HardGateChecker.check_top3_not_dominant(self, baseline_returns: np.ndarray, candidate_returns: np.ndarray)`
- L421 `HardGateChecker.check_jackknife_stable(self, baseline_returns: np.ndarray, candidate_returns: np.ndarray)`
- L428 `HardGateChecker.check_cost_100bp_improves(self, baseline_net_100bp: np.ndarray, candidate_net_100bp: np.ndarray)`
- L435 `HardGateChecker.check_any_failure_is_fatal(self)`
- L445 `HardGateChecker.verdict(self)`

## scripts/migrate_factor_cache.py

[打开文件](../../scripts/migrate_factor_cache.py)

- L32 `migrate(dry_run: bool=False, factor_name: str=None)`
- L88 `main()`

## scripts/monitor_photoresist_panic.py

[打开文件](../../scripts/monitor_photoresist_panic.py)

- L34 `parse_args()`
- L47 `_load_yaml(path: Path)`
- L52 `classify_severity(triggered: bool, basket_return: float, percentile: float, breadth: float, config: dict)`
- L70 `data_is_stale(latest_date: int, requested_date: int, max_days: int)`
- L76 `_refresh_prices(prices: pd.DataFrame, codes: list[str], start: int, end: int)`
- L106 `_refresh_indices(index_prices: pd.DataFrame, codes: list[str], start: int, end: int)`
- L134 `_candidate_snapshot(prices: pd.DataFrame, universe: pd.DataFrame, event_date: int)`
- L155 `_render_report(alert: dict)`
- L177 `main()`

## scripts/panic_fast_check.py

[打开文件](../../scripts/panic_fast_check.py)

- L21 `load_fwd()`
- L47 `load_factor(fname)`
- L63 `compute_ic(merged)`
- L74 `event_spread(merged, direction, sig_type)`
- L95 `val_pos_years(merged, direction, sig_type)`

## scripts/panic_gate_shared.py

[打开文件](../../scripts/panic_gate_shared.py)

- L51 `build_trading_calendar(prices: pd.DataFrame)`
- L55 `load_market_calendar(root: str | Path, start: int, end: int)`
- L87 `trading_day_offset(calendar: np.ndarray, date: int, offset: int)`
- L97 `first_trading_day_of_year(calendar: np.ndarray, year: int)`
- L104 `build_exec_date_map(calendar: np.ndarray, lag: int=1)`
- L114 `class WindowSpec`
- L121 `WindowSpec.name(self)`
- L127 `class LeakageAudit`
- L147 `LeakageAudit.to_dict(self)`
- L151 `split_train_test(daily_basket: pd.DataFrame, window: WindowSpec, calendar: np.ndarray, leakage_control: str='label_available_plus_embargo', embargo_days: int=EMBARGO_DAYS, calendar_source: str='', calendar_is_full_market: bool=False)`
- L253 `get_windows()`
- L257 `validate_leakage_audit(audits: list[dict])`

## scripts/panic_walkforward_validate.py

[打开文件](../../scripts/panic_walkforward_validate.py)

- L37 `load_fwd()`
- L49 `load_factor(fname)`
- L69 `compute_ic(merged)`
- L82 `event_net_spread(merged, direction, sig_type)`

## scripts/predict_panic_ab_pretrade.py

[打开文件](../../scripts/predict_panic_ab_pretrade.py)

- L71 `parse_args()`
- L90 `_read_parquet_columns(path: Path, columns: Sequence[str] | None=None)`
- L100 `_normalize(df: pd.DataFrame)`
- L111 `_iter_year_dirs(base: Path, start: int, end: int)`
- L124 `_consecutive_true(flags: pd.Series)`
- L131 `_safe_auc(y_true, score)`
- L143 `_safe_pr_auc(y_true, score)`
- L156 `build_trading_calendar(prices: pd.DataFrame)`
- L160 `trading_day_offset(calendar: np.ndarray, date: int, offset: int)`
- L171 `first_trading_day_of_year(calendar: np.ndarray, year: int)`
- L180 `load_price_data(root: Path, start: int, end: int)`
- L199 `load_daily_basic(root: Path, start: int, end: int)`
- L225 `load_factor(root: Path, factor_name: str, start: int, end: int)`
- L257 `_forward_min(values: pd.Series, window: int)`
- L265 `compute_forward_metrics(prices: pd.DataFrame)`
- L292 `assign_drop_ab_labels(df: pd.DataFrame, retention_threshold: float)`
- L314 `compute_price_features(prices: pd.DataFrame)`
- L338 `validate_features(feature_cols: Sequence[str])`
- L349 `build_samples(root: Path, factor_name: str, start: int, end: int, retention_threshold: float, include_daily_basic: bool=False)`
- L407 `build_exec_date_map(prices: pd.DataFrame, lag: int=1)`
- L413 `build_model(random_state: int=42)`
- L433 `class SelectionMetrics`
- L446 `SelectionMetrics.to_dict(self)`
- L452 `compute_selection_metrics(df: pd.DataFrame, selected_mask: pd.Series | np.ndarray, action_name: str, cost: float=COST_BPS)`
- L489 `baseline_mask(df: pd.DataFrame)`
- L498 `class WindowSpec`
- L505 `WindowSpec.name(self)`
- L509 `get_windows()`
- L513 `run_walkforward(samples: pd.DataFrame, feature_cols: Sequence[str], calendar: np.ndarray, windows: Sequence[WindowSpec] | None=None, min_coverage: float=0.05, leakage_control: str='label_available_plus_embargo', embargo_days: int=20)`
- L733 `summarize_status(walk: pd.DataFrame, min_coverage: float=0.05)`
- L784 `compute_diagnostics(predictions: pd.DataFrame, strategy_df: pd.DataFrame)`
- L870 `_to_markdown_table(frame: pd.DataFrame)`
- L888 `generate_report(factor_name: str, retention_threshold: float, feature_cols: Sequence[str], walk: pd.DataFrame, strategy: pd.DataFrame, leakage_audit: list[dict], feature_set: str, leakage_control: str, embargo_days: int, min_coverage: float=0.05, diagnostics: pd.DataFrame | None=None, block_reasons: list[str] | None=None)`
- L1040 `save_outputs(out_dir: Path, predictions: pd.DataFrame, walk: pd.DataFrame, strategy: pd.DataFrame, importance: pd.DataFrame, baseline: pd.DataFrame, leakage: list[dict], diagnostics: pd.DataFrame, report: str, manifest: dict)`
- L1069 `main()`

## scripts/preflight_index_universe_exec.py

[打开文件](../../scripts/preflight_index_universe_exec.py)

- L37 `_off_main(codes)`
- L41 `_fail(msg: str)`
- L46 `check_ratios()`
- L57 `check_window(start: str, end: str, tag: str)`
- L135 `check_mini_backtest()`
- L180 `main()`

## scripts/preflight_sector_panic_entry_confirmation_r0.py

[打开文件](../../scripts/preflight_sector_panic_entry_confirmation_r0.py)

- L45 `_imports()`
- L68 `_load_yaml(path: Path)`
- L75 `_locked_path(relative: str)`
- L84 `validate_scope_contract(scope: dict)`
- L185 `verify_locked_inputs(scope: dict)`
- L208 `validate_parent_semantics(scope: dict)`
- L245 `_synthetic_panel(codes: list[str], calendar: np.ndarray, t1_closes: dict[str, float])`
- L270 `_synthetic_selection(codes: list[str])`
- L283 `synthetic_semantic_proof(scope: dict)`
- L379 `verify_runtime(scope: dict, runtime_dir: Path, locked_manifest_id: str)`
- L414 `run(scope_path: Path, runtime_a: Path, runtime_b: Path, output_dir: Path)`
- L462 `main()`

## scripts/preflight_sector_panic_r7.py

[打开文件](../../scripts/preflight_sector_panic_r7.py)

- L20 `sha256_file(path: Path)`
- L28 `_read_csv(path: Path, usecols: list[str])`
- L34 `_unique_event_frame(events: pd.DataFrame)`
- L45 `_sector_counts(events: pd.DataFrame, pairs: pd.DataFrame)`
- L74 `_time_order_counts(events: pd.DataFrame, episodes: pd.DataFrame)`
- L100 `run(scope_path: Path, replay_dir: Path, output_dir: Path)`
- L190 `main()`

## scripts/prepare_sector_panic_data.py

[打开文件](../../scripts/prepare_sector_panic_data.py)

- L65 `_parse_date(value: str, label: str)`
- L73 `completed_month_end(end_date: str)`
- L82 `month_ends(start_date: str, end_date: str)`
- L96 `missing_evidence_fields(member: dict)`
- L108 `_atomic_write_json(path: Path, payload: dict)`
- L126 `load_research_contracts()`
- L201 `_weight_frame(client, start_date: str, end_date: str)`
- L216 `_sane_weight_months(client, frame: pd.DataFrame, index_code: str)`
- L230 `prepare_weights(client, sectors: dict[str, dict], start_date: str, weights_end: str)`
- L285 `audit_weights(client, sectors: dict[str, dict], start_date: str, weights_end: str)`
- L317 `official_codes_from_weights(client, sectors: dict[str, dict], start_date: str, weights_end: str)`
- L336 `membership_days_by_code(client, sectors: dict[str, dict], codes: list[str], start_date: str, end_date: str, weights_end: str)`
- L389 `prepare_metadata(client, codes: list[str], start_date: str, end_date: str)`
- L426 `audit_sparse_metadata(client, codes: list[str], start_date: str, end_date: str)`
- L457 `expected_days_by_code(client, codes: Iterable[str], start_date: str, end_date: str)`
- L551 `_cached_key_sets(client, table_name: str, codes: list[str], start_date: str, end_date: str)`
- L578 `prepare_raw_prices(client, codes: list[str], expected: dict[str, set[int]], start_date: str, end_date: str)`
- L691 `prepare_adj_factors(client, codes: list[str], start_date: str, end_date: str, date_query_threshold: int=20)`
- L793 `rebuild_adjusted_prices(client, codes: list[str], start_date: str, end_date: str, batch_size: int=40)`
- L881 `prepare_prices(client, codes: list[str], expected: dict[str, set[int]], start_date: str, end_date: str)`
- L897 `prepare_indices(client, index_codes: list[str], start_date: str, end_date: str)`
- L968 `prepare_limits(client, codes: list[str], expected: dict[str, set[int]], start_date: str, end_date: str)`
- L1055 `_dense_coverage(client, table_name: str, codes: list[str], expected: dict[str, set[int]], start_date: str, end_date: str)`
- L1085 `_raw_coverage(client, codes: list[str], expected: dict[str, set[int]], start_date: str, end_date: str)`
- L1124 `_audit_adjustment_math(client, codes: list[str], start_date: str, end_date: str, batch_size: int=50)`
- L1187 `audit_indices(client, index_codes: list[str], open_days: list[int], start_date: str, end_date: str)`
- L1216 `run_audit(client, sectors: dict[str, dict], manual: dict, official_codes: list[str], market_data_codes: list[str], index_codes: list[str], expected: dict[str, set[int]], start_date: str, end_date: str, weights_end: str)`
- L1293 `_parse_stages(value: str)`
- L1301 `parse_args(argv: list[str] | None=None)`
- L1319 `main(argv: list[str] | None=None)`

## scripts/probe_industry_pit.py

[打开文件](../../scripts/probe_industry_pit.py)

- L25 `main()`
- L135 `_write(report: dict)`

## scripts/probe_sector_panic_e2_audit_v2_20260922.py

[打开文件](../../scripts/probe_sector_panic_e2_audit_v2_20260922.py)

- L12 `main()`

## scripts/probe_sector_panic_e2_audit_v3_20260922.py

[打开文件](../../scripts/probe_sector_panic_e2_audit_v3_20260922.py)

- L14 `main()`

## scripts/probe_sector_panic_e2_r3_audit_20260922.py

[打开文件](../../scripts/probe_sector_panic_e2_r3_audit_20260922.py)

- L12 `main()`

## scripts/pull_csi300_daily_basic.py

[打开文件](../../scripts/pull_csi300_daily_basic.py)

- L32 `_universe()`
- L41 `main()`

## scripts/pull_fina_indicator_history.py

[打开文件](../../scripts/pull_fina_indicator_history.py)

- L27 `get_universe_stocks()`
- L50 `main()`

## scripts/pull_monthly_weights.py

[打开文件](../../scripts/pull_monthly_weights.py)

- L27 `main()`

## scripts/pull_phase0_data.py

[打开文件](../../scripts/pull_phase0_data.py)

- L31 `_pull_index_daily(client, code: str, name: str, start_date: str, end_date: str)`
- L55 `main(argv: list[str] | None=None)`

## scripts/pull_product_market_data.py

[打开文件](../../scripts/pull_product_market_data.py)

- L26 `main()`

## scripts/pull_statement_history.py

[打开文件](../../scripts/pull_statement_history.py)

- L35 `_universe()`
- L46 `_periods(start_year: int, end_year: int)`
- L54 `main()`

## scripts/rebuild_daily_basic_factors.py

[打开文件](../../scripts/rebuild_daily_basic_factors.py)

- L23 `_cs_zscore(s: pd.Series)`
- L38 `_write(loader, name: str, df: pd.DataFrame, col: str, force: bool)`
- L56 `main()`

## scripts/rebuild_feasibility_report.py

[打开文件](../../scripts/rebuild_feasibility_report.py)

- L52 `main()`

## scripts/rebuild_index_weight_coverage.py

[打开文件](../../scripts/rebuild_index_weight_coverage.py)

- L44 `_phase0_identity(raw: pd.DataFrame)`
- L60 `_sane(n_stocks: int, weight_sum: float | None, weight_required: bool=False, negative_weights: bool=False)`
- L83 `_snapshot_stats(snapshot: pd.DataFrame, code_col: str, has_weight: bool)`
- L116 `main()`

## scripts/rebuild_monthly_overlap.py

[打开文件](../../scripts/rebuild_monthly_overlap.py)

- L43 `main()`

## scripts/reconcile_sector_panic_rebuild_diagnostic.py

[打开文件](../../scripts/reconcile_sector_panic_rebuild_diagnostic.py)

- L14 `_load(run_dir: Path, name: str)`
- L19 `_finite(value)`
- L27 `_comp_key(row: dict, *, with_signal: bool=False)`
- L33 `reconcile(run_dir: Path, *, entry_cost=0.005, exit_cost=0.005, tol=1e-09)`
- L250 `main()`

## scripts/regime_failure_attribution.py

[打开文件](../../scripts/regime_failure_attribution.py)

- L26 `_pct(x: Any, digits: int=1)`
- L32 `_num(x: Any, digits: int=2)`
- L38 `_parse_mapping(value: Any)`
- L60 `_compound(series: pd.Series)`
- L67 `_idxmax_label(values: pd.Series)`
- L75 `_load_run_index(runs_csv: Path, years: list[int])`
- L85 `_load_period_returns(run_dir: Path, strategy: str, year: int)`
- L104 `_load_holdings(run_dir: Path, strategy: str, year: int)`
- L117 `_read_prices_for_dates(dates: set[int])`
- L131 `_stock_contributions(holdings: pd.DataFrame)`
- L183 `_load_regime_monthly(run_dir: Path, year: int)`
- L211 `_holdings_overlap(holdings: dict[tuple[int, str], pd.DataFrame])`
- L254 `_write_report(out_doc: Path, run_index: pd.DataFrame, monthly: pd.DataFrame, regime_monthly: pd.DataFrame, contrib_summary: pd.DataFrame, overlap: pd.DataFrame)`
- L388 `main()`

## scripts/regime_parameter_grid.py

[打开文件](../../scripts/regime_parameter_grid.py)

- L110 `_set_nested(config: dict[str, Any], dotted_path: str, value: Any)`
- L118 `_pct(value: Any, digits: int=1)`
- L124 `_num(value: Any, digits: int=2)`
- L130 `_load_json(path: Path)`
- L134 `_new_run_dir(before: set[Path])`
- L141 `_collect_sleeve_means(run_dir: Path)`
- L150 `_collect_regime_means(run_dir: Path)`
- L159 `_collect_overlay_multiplier_means(run_dir: Path)`
- L168 `_read_year_partitions(dataset: str, years: set[int], columns: list[str])`
- L179 `_next_trade_date(trade_dates: list[int], date: int)`
- L186 `_annualized_return(period_returns: pd.Series)`
- L193 `_information_ratio(returns: pd.Series)`
- L203 `_max_drawdown(period_returns: pd.Series)`
- L212 `_fast_backtest(composite: pd.DataFrame, start: str, end: str, top_n: int)`
- L319 `_run_fast_case(cfg_path: Path, start: str, end: str, top_n: int)`
- L360 `_write_summary(out_doc: Path, rows: list[dict[str, Any]])`
- L444 `main()`

## scripts/repair_adj_factor.py

[打开文件](../../scripts/repair_adj_factor.py)

- L53 `_parse_date(s: str)`
- L57 `_scan_partition_files(part_path: Path)`
- L73 `_normalize_schema(df: pd.DataFrame)`
- L103 `_find_duplicates(part_path: Path)`
- L181 `dedup_partition(part_path: Path, dry_run: bool=False, years_filter: Optional[Set[int]]=None)`
- L288 `derive_adj_factor_from_prices(year: int, prices_raw_base: Path, prices_adj_base: Path, adj_factor_base: Path, dry_run: bool=False)`
- L377 `main()`

## scripts/repair_cache.py

[打开文件](../../scripts/repair_cache.py)

- L26 `repair_limit_status(start: str, end: str, dry_run: bool=False)`
- L120 `main()`

## scripts/repair_fundamental_factors.py

[打开文件](../../scripts/repair_fundamental_factors.py)

- L134 `_load_parquet_source(source_name: str)`
- L159 `_load_price_daily(start: str, end: str)`
- L200 `_compute_available_date(end_date: int, ann_date=None)`
- L218 `_precompute_ttm_values(source: pd.DataFrame, field: str, agg: str='sum')`
- L283 `_precompute_growth_ttm(source: pd.DataFrame, field: str, min_quarters: int=4)`
- L350 `_precompute_stability_8q(source: pd.DataFrame, field: str, min_quarters: int=4)`
- L395 `_precompute_acceleration(source: pd.DataFrame, field: str, min_quarters: int=6)`
- L457 `_precompute_latest(source: pd.DataFrame, field: str)`
- L479 `_precompute_composite_avg(source: pd.DataFrame, fields: List[str])`
- L528 `_pit_align(precomputed: pd.DataFrame, trade_dates: pd.DataFrame, sign: int=1, factor_name: str='')`
- L598 `_apply_cs_winsorize_zscore(df: pd.DataFrame)`
- L636 `_write_factor_cache(df: pd.DataFrame, factor_name: str, force: bool=False)`
- L673 `_write_manifest(factor_name: str, stats: dict)`
- L695 `main()`

## scripts/repair_price_interior_gaps.py

[打开文件](../../scripts/repair_price_interior_gaps.py)

- L29 `_load_have(table: str, start: int, end: int)`
- L42 `_load_suspend(start: int, end: int)`
- L59 `plan_holes(start: str, end: str)`
- L76 `_write_merged(cache, table: str, df: pd.DataFrame, partition_cols: list[str])`
- L87 `run(start: str, end: str, *, dry_run: bool, out_dir: Path)`
- L194 `main()`

## scripts/replay_photoresist_panic_alert.py

[打开文件](../../scripts/replay_photoresist_panic_alert.py)

- L33 `parse_args()`
- L45 `main()`

## scripts/report_sector_panic_r4_stock_sells.py

[打开文件](../../scripts/report_sector_panic_r4_stock_sells.py)

- L27 `sha256(path: Path)`
- L35 `require_unique(frame: pd.DataFrame, keys: list[str], label: str)`
- L41 `safe_rate(values: pd.Series)`
- L46 `reason_metric(group: pd.DataFrame, reason: str, metric: str)`
- L64 `aggregate_stock(group: pd.DataFrame)`
- L106 `aggregate_avwap(group: pd.DataFrame)`
- L133 `render_avwap_markdown(frame: pd.DataFrame)`
- L175 `main()`

## scripts/review_sector_panic_e2_full214_20260922.py

[打开文件](../../scripts/review_sector_panic_e2_full214_20260922.py)

- L18 `main()`

## scripts/review_sector_panic_e2_r3_20260922.py

[打开文件](../../scripts/review_sector_panic_e2_r3_20260922.py)

- L16 `sha(path)`
- L20 `main()`

## scripts/review_v10_action_value_r1_implementation.py

[打开文件](../../scripts/review_v10_action_value_r1_implementation.py)

- L19 `main()`

## scripts/review_v10_cqf_claims.py

[打开文件](../../scripts/review_v10_cqf_claims.py)

- L18 `sha(path)`
- L22 `main()`

## scripts/review_v10_sector_split_claims.py

[打开文件](../../scripts/review_v10_sector_split_claims.py)

- L33 `_hdr(n: str, t: str)`
- L37 `_pct(x: float)`
- L41 `load()`
- L48 `section_1_sample(p: pd.DataFrame)`
- L62 `section_2_sectors(p: pd.DataFrame, d: pd.DataFrame)`
- L95 `section_3_deployment(p: pd.DataFrame)`
- L114 `section_4_breadth(p: pd.DataFrame, d: pd.DataFrame)`
- L148 `buy_fills()`
- L160 `section_5_timing(p: pd.DataFrame)`
- L187 `section_6_overlap(p: pd.DataFrame)`
- L228 `section_7_exits()`
- L252 `section_8_mechanism()`
- L284 `section_9_concentration(p: pd.DataFrame)`
- L294 `main()`

## scripts/run_frozen_product_compare.py

[打开文件](../../scripts/run_frozen_product_compare.py)

- L49 `_sha256(path: Path)`
- L55 `write_manifest()`
- L82 `_run(cmd: list[str])`
- L89 `classify_product(summary: dict)`
- L103 `write_decision(results: dict)`
- L138 `main()`

## scripts/run_lowvol_full_constituent_universe.py

[打开文件](../../scripts/run_lowvol_full_constituent_universe.py)

- L69 `_sha256(path: Path)`
- L75 `_write_json(path: Path, obj)`
- L81 `hash_parquet_tree(rel: str)`
- L95 `hash_all_inputs()`
- L102 `assert_fresh_run_dir(out_root: Path)`
- L112 `write_manifest(out_root: Path, extra: dict | None=None, *, hash_inputs: bool=True)`
- L158 `write_decision(out_root: Path, rows: list[dict])`
- L188 `lowvol_scores(price_start: str, price_end: str)`
- L205 `run_one(scores: pd.DataFrame, start: str, end: str, index_code: str, out_root: Path)`
- L234 `_run(cmd: list[str])`
- L241 `run_analysis(out_root: Path)`
- L263 `main()`

## scripts/run_lowvol_residual_attribution.py

[打开文件](../../scripts/run_lowvol_residual_attribution.py)

- L53 `weights_doc_path(weights: Path, root: Path=ROOT)`
- L60 `_load_nav(path: Path)`
- L74 `_load_index_weight(index_code: str='000300.SH')`
- L93 `_asof(dates: list[int], query: int)`
- L98 `_load_factor(name: str)`
- L113 `_index_px(index_code: str='000300.SH', prefer: str='open')`
- L127 `_fwd_ret(prices: pd.DataFrame, dates: list[int], horizon: int)`
- L152 `main()`

## scripts/run_p0_after_pull.py

[打开文件](../../scripts/run_p0_after_pull.py)

- L13 `_run(script: str, extra: list[str] | None=None)`
- L21 `main()`

## scripts/run_p0_pipeline.py

[打开文件](../../scripts/run_p0_pipeline.py)

- L23 `_run(script: str, extra: list[str] | None=None)`
- L31 `main()`

## scripts/run_photoresist_panic_alert.py

[打开文件](../../scripts/run_photoresist_panic_alert.py)

- L35 `parse_args()`
- L56 `main()`

## scripts/run_product_backtests.py

[打开文件](../../scripts/run_product_backtests.py)

- L40 `_load_factor(name: str, start: str, end: str)`
- L54 `_write_json(path: Path, obj)`
- L60 `_summ_to_json(s: dict)`
- L64 `run_lowvol(start: str, end: str, index_code: str='000300.SH')`
- L87 `_cached_index_codes(exclude: set[str] | None=None)`
- L101 `_index_panel(codes: list[str], start: str, end: str)`
- L137 `run_industry(start: str, end: str)`
- L175 `_etf_panel(start: str, end: str)`
- L210 `run_etf(start: str, end: str)`
- L233 `run_execution(start: str, end: str)`
- L271 `run_universe(start: str, end: str)`
- L284 `run_shadow(start: str, end: str)`
- L352 `_write_doc(results: dict)`
- L371 `main()`

## scripts/run_sector_panic_avwap_hwm_historical.py

[打开文件](../../scripts/run_sector_panic_avwap_hwm_historical.py)

- L85 `parse_args(argv=None)`
- L95 `_locked_path(relative: str)`
- L104 `_load_scope(path: Path)`
- L132 `_read_table(root: Path, name: str)`
- L140 `_validate_runtime(runtime: Path, scope: dict)`
- L159 `_policy(scope: dict, research: dict)`
- L186 `_add_daily_avwap_fields(panel: pd.DataFrame, raw_prices: pd.DataFrame)`
- L210 `_atomic_json(path: Path, payload: dict)`
- L226 `_canonical(name: str, frame: pd.DataFrame)`
- L234 `_atomic_csv(path: Path, name: str, frame: pd.DataFrame)`
- L254 `_write_outputs(out_dir: Path, outputs: dict[str, pd.DataFrame], summary: dict, source: dict)`
- L296 `_concat(frames: list[pd.DataFrame])`
- L301 `_sector_summary(valid: pd.DataFrame, sectors: list[str])`
- L323 `_exit_reason_summary(components: pd.DataFrame)`
- L339 `run_single(scope_path: Path, runtime_dir: Path, out_dir: Path)`
- L705 `verify_replay(left: Path, right: Path)`
- L721 `main(argv=None)`

## scripts/run_sector_panic_backtest.py

[打开文件](../../scripts/run_sector_panic_backtest.py)

- L66 `_ensure_builder_imports()`
- L84 `parse_args()`
- L110 `_read_partitioned(path: Path, start: int | None=None, end: int | None=None)`
- L139 `_load_weights(index_codes: list[str], start: int, end: int)`
- L154 `_read_runtime_table(runtime_dir: Path, name: str)`
- L162 `_hash_file(path: Path)`
- L166 `_status_sources(limit_status: pd.DataFrame | None, suspend_status: pd.DataFrame | None, stock_status: pd.DataFrame | None, namechange: pd.DataFrame | None, limit_status_missing_rows: int=0)`
- L203 `_count_runtime_limit_gaps(prices: pd.DataFrame, limit_status: pd.DataFrame | None, weight_codes: list[str], runtime_manifest: dict)`
- L248 `_suspended_keys(suspend_status: pd.DataFrame | None)`
- L263 `_entry_codes(universe: pd.DataFrame, signal_date: int, entry_date: int, prices: pd.DataFrame, calendar: np.ndarray, eligibility: dict, limit_status: pd.DataFrame | None, suspend_status: pd.DataFrame | None, stock_status: pd.DataFrame | None, namechange: pd.DataFrame | None, min_components: int, eligible_by_date: dict[int, list[str]] | None=None, suspended_by_date: dict[int, set[str]] | None=None)`
- L327 `_exit_checker(codes: list[str], prices: pd.DataFrame, limit_status: pd.DataFrame | None, suspend_status: pd.DataFrame | None)`
- L346 `_regime_map(parent_index: pd.DataFrame)`
- L363 `_build_efficient_basket(prices: pd.DataFrame, universe: pd.DataFrame, calendar: np.ndarray, eligibility: dict, max_single_weight: float, min_components: int, limit_status: pd.DataFrame | None, suspend_status: pd.DataFrame | None, stock_status: pd.DataFrame | None, namechange: pd.DataFrame | None)`
- L538 `_write_sector_outputs(sector_dir: Path, config, universe: pd.DataFrame, signal: pd.DataFrame, events: pd.DataFrame, ledger: pd.DataFrame, summary: pd.DataFrame, annual: pd.DataFrame, manifest: dict)`
- L570 `run_sector(config_path: Path, start: int, end: int, out_dir: Path, strict_tradability: bool, runtime_data_dir: Path | None=None, path_horizon: int=0, verified_runtime: VerifiedRuntimeSnapshot | None=None)`
- L912 `_write_comparison(results: list[dict], out_dir: Path)`
- L965 `main()`

## scripts/run_sector_panic_component_exit.py

[打开文件](../../scripts/run_sector_panic_component_exit.py)

- L70 `parse_args(argv=None)`
- L80 `_read_table(root: Path, name: str)`
- L88 `_atomic_json(path: Path, payload: dict)`
- L104 `_canonical(name: str, frame: pd.DataFrame)`
- L112 `_atomic_csv(path: Path, name: str, frame: pd.DataFrame)`
- L129 `_locked_path(relative: str)`
- L138 `_load_scope(path: Path)`
- L163 `_candidate_rule(scope: dict)`
- L172 `_validate_runtime(runtime_dir: Path, scope: dict)`
- L182 `_policy(scope: dict, parent: dict)`
- L205 `_add_daily_avwap_fields(panel: pd.DataFrame, raw_prices: pd.DataFrame)`
- L232 `_revision(frame: pd.DataFrame, prefix: str, keys: list[str])`
- L245 `_pair_events(events: pd.DataFrame)`
- L262 `_pair_summary(paired: pd.DataFrame)`
- L277 `_component_summary(diag: pd.DataFrame)`
- L294 `_episode_reports(paired: pd.DataFrame, episodes: pd.DataFrame)`
- L318 `run_single(scope_path: Path, runtime_dir: Path, out_dir: Path)`
- L412 `verify_replay(left: Path, right: Path)`
- L422 `main(argv=None)`

## scripts/run_sector_panic_confirmation_close_v10.py

[打开文件](../../scripts/run_sector_panic_confirmation_close_v10.py)

- L75 `parse_args(argv=None)`
- L87 `_json_safe(value)`
- L99 `_workspace_path(relative: str)`
- L105 `_load_scope(path: Path)`
- L123 `_policy(scope: dict)`
- L141 `_concat(frames)`
- L146 `_simulate_spec(*, stock, policies, panels, calendar, boundaries, rule_id, policy, review_sessions=0, review_mode='NONE', buffer_natr=0.0, two_close=False, confirmation_close_floor=False)`
- L173 `_bootstrap(events: pd.DataFrame, *, seed: int, runs: int)`
- L195 `_arm_statistics(events, components, scope)`
- L269 `_gates(summary: pd.DataFrame, replay_ok: bool, scope: dict)`
- L301 `_baseline_replay_matches(components: pd.DataFrame, v8_source: Path, scope: dict)`
- L332 `_write_outputs(out_dir, outputs, summary, sources, dataset_sha)`
- L345 `run_single(scope_path, runtime_dir, r7_source, v8_source, out_dir)`
- L468 `main(argv=None)`

## scripts/run_sector_panic_confirmation_invalidation_v11.py

[打开文件](../../scripts/run_sector_panic_confirmation_invalidation_v11.py)

- L63 `_json_safe(value)`
- L75 `parse_args(argv=None)`
- L87 `_workspace_path(relative: str)`
- L93 `_forbid_v10_output(out_root: Path)`
- L105 `_validate_frozen_v10_source(v10_source: Path, scope: dict)`
- L169 `_load_scope(path: Path)`
- L201 `_simulate_v11(*, stock, policies, panels, calendar, boundaries, rule_id, policy)`
- L223 `_event_stats(arm: pd.DataFrame, control: pd.DataFrame, scope: dict)`
- L277 `_gates(scope, v10_events, v11_events, v10_double, v11_double, retention, *, v10_replay_verified: bool)`
- L321 `run_single(scope_path, runtime_dir, r7_source, v10_source, out_dir)`
- L461 `_report(summary: dict, gates: pd.DataFrame, retention: dict)`
- L496 `main(argv=None)`

## scripts/run_sector_panic_entry_avwap_forward.py

[打开文件](../../scripts/run_sector_panic_entry_avwap_forward.py)

- L75 `parse_args(argv=None)`
- L87 `_locked_path(relative: str)`
- L96 `_read_table(root: Path, name: str)`
- L104 `_load_scope(path: Path)`
- L130 `_manifest(root: Path)`
- L137 `_prefix_integrity(baseline: Path, candidate: Path, boundary: int, weights_boundary: int)`
- L165 `_validate_runtime(runtime: Path, baseline: Path, scope: dict)`
- L195 `_policy(scope: dict, research: dict)`
- L218 `_add_daily_avwap_fields(panel: pd.DataFrame, raw_prices: pd.DataFrame)`
- L241 `_empty_outputs()`
- L245 `_summary(scope: dict, status: str, manifest: dict, runtime_dataset_sha256: str | None=None, **extra)`
- L259 `_atomic_json(path: Path, payload: dict)`
- L275 `_canonical(name: str, frame: pd.DataFrame)`
- L283 `_atomic_csv(path: Path, name: str, frame: pd.DataFrame)`
- L300 `_write_outputs(out_dir: Path, outputs: dict[str, pd.DataFrame], summary: dict, source: dict)`
- L332 `run_single(scope_path: Path, runtime_dir: Path, baseline_dir: Path, out_dir: Path)`
- L617 `verify_replay(left: Path, right: Path)`
- L633 `main(argv=None)`

## scripts/run_sector_panic_entry_confirmation_r0_forward.py

[打开文件](../../scripts/run_sector_panic_entry_confirmation_r0_forward.py)

- L101 `parse_args(argv=None)`
- L114 `_locked_path(relative: str)`
- L123 `_read_table(root: Path, name: str)`
- L131 `_load_scope(path: Path)`
- L181 `_validate_implementation_lock(path: Path, scope_path: Path)`
- L214 `_manifest(root: Path)`
- L221 `_pit_prefix_frame(name: str, frame: pd.DataFrame, cutoff: int | None)`
- L242 `_prefix_integrity(baseline: Path, candidate: Path, boundary: int, weights_boundary: int)`
- L273 `_validate_runtime(runtime: Path, baseline: Path, scope: dict)`
- L314 `_policy(scope: dict, research: dict)`
- L337 `_add_daily_avwap_fields(panel: pd.DataFrame, raw_prices: pd.DataFrame)`
- L360 `_empty_outputs()`
- L364 `_tag_arm(frame: pd.DataFrame, arm: str)`
- L375 `_nearest_rank_q10(values: pd.Series)`
- L382 `_episode_bootstrap_mean_ci(episode_values: pd.Series, seed: int=BOOTSTRAP_SEED, runs: int=BOOTSTRAP_RUNS)`
- L399 `_positive_episode_concentration(episode_values: pd.Series)`
- L406 `_gate_pass(observed, spec: dict)`
- L428 `_revision_value(value)`
- L443 `_row_fingerprint(row: pd.Series | dict)`
- L454 `_ensure_logical_keys(name: str, frame: pd.DataFrame)`
- L495 `_read_previous_csv(output_dir: Path, name: str)`
- L502 `_apply_cross_runtime_revisions(outputs: dict[str, pd.DataFrame], output_dir: Path, batch_id: str)`
- L606 `_component_registry(selection: pd.DataFrame, gate: pd.DataFrame, result: dict[str, pd.DataFrame], arm: str)`
- L638 `_entry_price_diagnostics(selection: pd.DataFrame, gate: pd.DataFrame, reference: dict[str, pd.DataFrame], candidate: dict[str, pd.DataFrame])`
- L702 `_confirmation_summary(registry: pd.DataFrame, paired: pd.DataFrame)`
- L775 `_build_portfolio_overlay(registry: pd.DataFrame, inventory: pd.DataFrame, scope: dict, calendar)`
- L961 `_forward_detected(detected: pd.DataFrame, start: int, end: int)`
- L971 `_simulate_r8_candidate(sector: str, event_id: str, signal_date: int, gate_observation_date: int, entry_date: int, selection: pd.DataFrame, panel: pd.DataFrame, calendar, policy: ComponentPolicy, next_event_entry_date: int | None=None, revision_batch_id: str='R8_ENTRY_CONFIRMATION_FORWARD')`
- L993 `_ensure_e1_daily_from_t1(result: dict[str, pd.DataFrame], sector: str, event_id: str, signal_date: int, gate_observation_date: int, entry_date: int, event_capital: float, revision_batch_id: str)`
- L1037 `_e2_fixed_diagnostics(selection: pd.DataFrame, gate: pd.DataFrame, candidate: dict[str, pd.DataFrame], panel: pd.DataFrame, calendar, sector: str, event_id: str, signal_date: int, gate_observation_date: int, entry_date: int)`
- L1189 `_summary(scope: dict, status: str, manifest: dict, runtime_dataset_sha256: str | None=None, **extra)`
- L1204 `_atomic_json(path: Path, payload: dict)`
- L1220 `_canonical(name: str, frame: pd.DataFrame)`
- L1228 `_atomic_csv(path: Path, name: str, frame: pd.DataFrame)`
- L1245 `_write_outputs(out_dir: Path, outputs: dict[str, pd.DataFrame], summary: dict, source: dict)`
- L1277 `run_single(scope_path: Path, runtime_dir: Path, baseline_dir: Path, out_dir: Path, implementation_lock_path: Path=DEFAULT_IMPLEMENTATION_LOCK)`
- L1837 `verify_replay(left: Path, right: Path)`
- L1853 `main(argv=None)`

## scripts/run_sector_panic_entry_exit_attribution.py

[打开文件](../../scripts/run_sector_panic_entry_exit_attribution.py)

- L165 `parse_args(argv=None)`
- L180 `_json_safe(value)`
- L204 `_workspace_path(relative: object)`
- L213 `_forbid_frozen_outputs(out_root: Path)`
- L227 `_forbid_frozen_output(out_root: Path)`
- L233 `_forbid_v10_output(out_root: Path)`
- L239 `_require_matrix_output_root(out_root: Path)`
- L254 `_load_scope(path: Path)`
- L361 `_read_csv(path: Path)`
- L367 `_safe_manifest_output(root: Path, manifest: dict, name: str)`
- L386 `_validate_frozen_source(source: Path, *, required_outputs: Iterable[str], expected_manifest_sha256: str | None=None, expected_output_hashes: Mapping[str, str] | None=None)`
- L412 `_source_lock(scope: dict, key: str)`
- L419 `_locked_file(scope: dict, key: str, *, require: bool=True)`
- L442 `_validate_locked_manifest_file(scope: dict, key: str, *, expected_root: Path | None=None, require_complete: bool=True)`
- L460 `_validate_controls(scope: dict, v10_source: Path, v11_source: Path, v12_source: Path, *, v10_source_b: Path=DEFAULT_V10_SOURCE_B)`
- L614 `_policy_from_v10_scope(v10_scope: dict)`
- L623 `_load_replay_context(runtime_dir: Path, r7_source: Path, v10_scope: dict)`
- L663 `_validate_runtime_manifest_lock(scope: dict, runtime_dir: Path, key: str)`
- L684 `_validate_frozen_b0_contract(controls: dict, scope: dict, *, v10_key: str='v10')`
- L778 `_concat(frames: Iterable[pd.DataFrame])`
- L783 `_simulate_overlay(context: dict, *, overlay: str, double_cost: bool=False)`
- L817 `_simulate_b0_baseline(context: dict, *, double_cost: bool=False)`
- L857 `_event_with_episode(components: pd.DataFrame, context: dict)`
- L863 `_filter_rule(frame: pd.DataFrame, rule_id: str)`
- L869 `_validate_frozen_cell_counts(controls: dict)`
- L889 `_validate_read_only_control_relationships(controls: dict)`
- L904 `_frozen_filter_decomposition(controls: dict)`
- L946 `_deployment_integrity(overlay_events: pd.DataFrame, b0_events: pd.DataFrame, *, tolerance: float=1e-12)`
- L986 `_assert_baseline_replay(replayed_component: pd.DataFrame, frozen_component: pd.DataFrame)`
- L1070 `_daily_metrics(daily: pd.DataFrame)`
- L1111 `_exit_mix(components: pd.DataFrame)`
- L1118 `_cell_metrics(*, entry: str, exit_name: str, rule_id: str, components: pd.DataFrame, events: pd.DataFrame, parent_events: pd.DataFrame, parent_components: pd.DataFrame, doubled_components: pd.DataFrame | None=None, doubled_events: pd.DataFrame | None=None, doubled_parent_events: pd.DataFrame | None=None, daily: pd.DataFrame | None=None, winner_retention: dict | None=None, source: str='new_simulation')`
- L1200 `_bool_series(series: pd.Series)`
- L1206 `_frozen_b0_control_cells(controls: dict, *, v10_key: str='v10')`
- L1221 `compile_existing_cells(*, v10_source: Path=DEFAULT_V10_SOURCE, v11_source: Path=DEFAULT_V11_SOURCE, v12_source: Path=DEFAULT_V12_SOURCE)`
- L1454 `assemble_matrix_cells(skeleton: pd.DataFrame, replacements: Mapping[tuple[str, str], Mapping[str, object]])`
- L1539 `_gate_rows(*, source_hashes_ok: bool, fill_v11_ok: bool, fill_v12_ok: bool, deployment_v11_ok: bool, deployment_v12_ok: bool, data_failures: int, unresolved: int, dual_runtime_ok: bool | None=None, frozen_b0_contract_ok: bool=True, baseline_fill_ok: bool=True, baseline_replay_ok: bool=True, baseline_deployment_ok: bool=True, baseline_double_deployment_ok: bool=True)`
- L1590 `_write_csv(path: Path, frame: pd.DataFrame, name: str)`
- L1608 `_output_sort_keys(name: str, frame: pd.DataFrame)`
- L1630 `_write_json(path: Path, payload: object)`
- L1643 `_finalize_runtime_gate(out_dir: Path, *, dual_runtime_ok: bool)`
- L1732 `run_single(scope_path: Path, runtime_dir: Path, r7_source: Path, v10_source: Path, v11_source: Path, v12_source: Path, out_dir: Path, *, v10_source_b: Path | None=None, dual_runtime_ok: bool | None=None)`
- L2089 `verify_replay(left: Path, right: Path)`
- L2119 `main(argv=None)`

## scripts/run_sector_panic_entry_review_buffer_v9.py

[打开文件](../../scripts/run_sector_panic_entry_review_buffer_v9.py)

- L71 `parse_args(argv=None)`
- L83 `_json_safe(value)`
- L95 `_workspace_path(relative: str)`
- L101 `_load_scope(path: Path)`
- L119 `_policy(scope: dict)`
- L137 `_concat(frames)`
- L142 `_simulate_spec(*, stock, policies, panels, calendar, boundaries, rule_id, policy, review_sessions=0, review_mode='NONE', buffer_natr=0.0, two_close=False)`
- L167 `_bootstrap(events: pd.DataFrame, *, seed: int, runs: int)`
- L189 `_arm_statistics(events, components, scope)`
- L262 `_gates(summary: pd.DataFrame, replay_ok: bool, scope: dict)`
- L294 `_baseline_replay_matches(components: pd.DataFrame, v8_source: Path, scope: dict)`
- L325 `_write_outputs(out_dir, outputs, summary, sources, dataset_sha)`
- L338 `run_single(scope_path, runtime_dir, r7_source, v8_source, out_dir)`
- L458 `main(argv=None)`

## scripts/run_sector_panic_extension_no_chase_v8.py

[打开文件](../../scripts/run_sector_panic_extension_no_chase_v8.py)

- L99 `parse_args(argv=None)`
- L110 `_workspace_path(relative: str)`
- L119 `_json_safe(value)`
- L131 `_load_scope(path: Path)`
- L154 `_validate_runtime(runtime: Path, scope: dict)`
- L170 `_read_r7_source(root: Path, scope: dict)`
- L196 `_policy(scope: dict)`
- L214 `_concat(items: list[pd.DataFrame])`
- L219 `_source_arm(frame: pd.DataFrame, source_rule: str, target_rule: str)`
- L228 `_first_finite(*values: object)`
- L239 `_next_boundaries(events: pd.DataFrame, calendar: np.ndarray)`
- L251 `_policy_map(policies: pd.DataFrame, rule_id: str)`
- L260 `_arm_input(row: dict, policy_row: dict, source_arm: str)`
- L308 `_simulate_spec(*, stock_panel: pd.DataFrame, policies: pd.DataFrame, panels: dict[str, pd.DataFrame], calendar: np.ndarray, boundaries: dict[tuple[str, str], int], rule_id: str, source_rule_id: str, source_arm: str, entry_mode: str, structural_exit: bool, policy: V8Policy)`
- L350 `_compact_components(frame: pd.DataFrame, prefix: str)`
- L362 `_no_chase_counterfactual(components: pd.DataFrame, states: pd.DataFrame, positions: dict[int, int])`
- L416 `_structural_counterfactual(components: pd.DataFrame)`
- L441 `_paired_events(events: pd.DataFrame, context: pd.DataFrame)`
- L489 `_episode_slot_statistics(components: pd.DataFrame, stock_context: pd.DataFrame)`
- L524 `_sign_flip_pvalue(values: pd.Series, seed: int, runs: int)`
- L535 `_gate_row(group: str, gate: str, observed, threshold, operator: str, passed: bool)`
- L546 `_statistics_and_gates(*, paired: pd.DataFrame, components: pd.DataFrame, double_events: pd.DataFrame, states: pd.DataFrame, stock_context: pd.DataFrame, scope: dict, replay_counts: dict)`
- L688 `_episode_summary(events: pd.DataFrame, context: pd.DataFrame)`
- L709 `_canonical(name: str, frame: pd.DataFrame)`
- L717 `_atomic_csv(path: Path, name: str, frame: pd.DataFrame)`
- L739 `_write_outputs(out_dir: Path, outputs: dict[str, pd.DataFrame], summary: dict, cohort: dict, sources: dict, dataset_sha: str)`
- L787 `verify_replay(left: Path, right: Path)`
- L808 `run_single(scope_path: Path, runtime_dir: Path, r7_source_root: Path, out_dir: Path)`
- L1059 `main(argv=None)`

## scripts/run_sector_panic_natr_stop_historical.py

[打开文件](../../scripts/run_sector_panic_natr_stop_historical.py)

- L94 `parse_args(argv=None)`
- L105 `_workspace_path(relative: str)`
- L114 `_load_scope(path: Path)`
- L135 `_validate_runtime(runtime: Path, scope: dict)`
- L150 `_read_e2_source(root: Path, scope: dict)`
- L181 `_build_panels(tables: dict[str, pd.DataFrame], selections: pd.DataFrame, calendar: np.ndarray)`
- L218 `_csv_bytes(name: str, frame: pd.DataFrame, columns: list[str] | None=None)`
- L235 `_verify_s0_frame(name: str, generated: pd.DataFrame, expected: pd.DataFrame, expected_path: Path)`
- L301 `_s0_policy(components: pd.DataFrame, confirmations: pd.DataFrame, entry_cost: float, exit_cost: float)`
- L339 `_enrich_s0_outputs(result_frames: dict[str, pd.DataFrame], policy: pd.DataFrame)`
- L361 `_event_context(frame: pd.DataFrame, source_events: pd.DataFrame)`
- L372 `_pair_events(events: pd.DataFrame)`
- L406 `_statistics(scope: dict, paired: pd.DataFrame, episodes: pd.DataFrame, doubled: pd.DataFrame)`
- L466 `_path_classification(components: pd.DataFrame)`
- L503 `_risk_overruns(components: pd.DataFrame, policies: pd.DataFrame, attempts: pd.DataFrame, panels: dict[str, pd.DataFrame], calendar: np.ndarray)`
- L566 `_cap20_shadow(components: pd.DataFrame, policies: pd.DataFrame)`
- L593 `_future_paths(components: pd.DataFrame, confirmations: pd.DataFrame, panels: dict[str, pd.DataFrame], calendar: np.ndarray)`
- L644 `_canonical(name: str, frame: pd.DataFrame)`
- L652 `_atomic_csv(path: Path, name: str, frame: pd.DataFrame)`
- L674 `_write_outputs(out_dir: Path, outputs: dict[str, pd.DataFrame], summary: dict, sources: dict, dataset_sha: str)`
- L711 `run_single(scope_path: Path, runtime_dir: Path, e2_source: Path, out_dir: Path)`
- L1025 `verify_replay(left: Path, right: Path)`
- L1043 `main(argv=None)`

## scripts/run_sector_panic_phase1.py

[打开文件](../../scripts/run_sector_panic_phase1.py)

- L79 `parse_args(argv: list[str] | None=None)`
- L89 `_read_table(root: Path, name: str)`
- L97 `_atomic_write_json(path: Path, payload: dict)`
- L118 `_canonicalize_frame(name: str, frame: pd.DataFrame)`
- L126 `_atomic_write_csv(path: Path, name: str, frame: pd.DataFrame)`
- L148 `_resolve_locked_path(relative: str)`
- L157 `_load_scope(scope_path: Path)`
- L206 `_validate_runtime(runtime_dir: Path, phase0b_scope_path: Path, scope: dict)`
- L217 `_phase1_policy(scope: dict, parent: dict)`
- L242 `_add_revision_columns(frame: pd.DataFrame, ledger_prefix: str, logical_columns: list[str])`
- L266 `_paired_events(event_ledger: pd.DataFrame)`
- L305 `_summarize_pairs(paired: pd.DataFrame)`
- L329 `_episode_diagnostics(paired: pd.DataFrame, episodes: pd.DataFrame, maximum_top_two_share: float)`
- L373 `_regime_summary(event_ledger: pd.DataFrame)`
- L392 `_basket_index_capture(event_ledger: pd.DataFrame, index_daily: pd.DataFrame, parent: dict)`
- L431 `_number_or_nan(value)`
- L439 `_overlap_ledger(inventory: pd.DataFrame)`
- L465 `_verify_required_outputs(scope: dict, outputs: dict[str, object])`
- L473 `run_single(scope_path: Path, runtime_dir: Path, out_dir: Path)`
- L771 `verify_replay_bytes(left: Path, right: Path)`
- L792 `main(argv: list[str] | None=None)`

## scripts/run_sector_panic_r7.py

[打开文件](../../scripts/run_sector_panic_r7.py)

- L64 `_read_table(root: Path, name: str)`
- L72 `_atomic_csv(path: Path, frame: pd.DataFrame)`
- L78 `_atomic_json(path: Path, payload: dict)`
- L83 `_add_daily_avwap_fields(panel: pd.DataFrame, raw_prices: pd.DataFrame)`
- L108 `_load_runtime(runtime_dir: Path, parent_scope: dict)`
- L126 `_component_policy(parent: dict)`
- L145 `_r7_policy(parent: dict)`
- L163 `_build_event_context(tables: dict[str, pd.DataFrame], calendar: np.ndarray, parent: dict, r7_scope: dict)`
- L261 `_nearest_q10(values: pd.Series)`
- L269 `_extend_episode_assignments(rows: pd.DataFrame, event_inputs: list[dict], nominal_episodes: pd.DataFrame)`
- L335 `_spearman(x: pd.Series, y: pd.Series)`
- L344 `_decision_diagnostics(predictions: pd.DataFrame, prediction_column: str='predicted_advantage', row_mask: pd.Series | None=None)`
- L378 `_paired_diagnostics(paired: pd.DataFrame)`
- L412 `_aggregate_daily(daily: pd.DataFrame)`
- L438 `run_single(scope_path: Path, runtime_dir: Path, output_dir: Path)`
- L714 `verify_replay(left: Path, right: Path)`
- L732 `main()`

## scripts/run_sector_panic_rebuild.py

[打开文件](../../scripts/run_sector_panic_rebuild.py)

- L36 `_out(run_id: str, kind: str='diagnostic')`
- L40 `cmd_preflight(args)`
- L59 `cmd_verify(args)`
- L82 `cmd_refuse_legacy(args)`
- L93 `cmd_refuse_hash_refresh(args)`
- L101 `main()`
- L147 `cmd_diagnostic(args)`
- L187 `cmd_synthetic(args)`

## scripts/run_sector_panic_repair_confirmation_historical.py

[打开文件](../../scripts/run_sector_panic_repair_confirmation_historical.py)

- L88 `parse_args(argv=None)`
- L98 `_read_table(root: Path, name: str)`
- L106 `_locked_path(relative: str)`
- L115 `_load_scope(path: Path)`
- L134 `_validate_runtime(runtime: Path, scope: dict)`
- L147 `_component_policy(scope: dict, parent: dict)`
- L164 `_repair_policy(scope: dict)`
- L178 `_add_daily_avwap_fields(panel: pd.DataFrame, raw_prices: pd.DataFrame)`
- L202 `_canonical(name: str, frame: pd.DataFrame)`
- L210 `_atomic_json(path: Path, payload: dict)`
- L226 `_atomic_csv(path: Path, name: str, frame: pd.DataFrame)`
- L246 `_legacy_gap_rows(sector: str, event_id: str, signal_date: int, gate: pd.DataFrame, confirmations: pd.DataFrame, panel: pd.DataFrame, calendar: np.ndarray)`
- L327 `_nearest_rank_q10(values: pd.Series)`
- L334 `_bootstrap_episode_lower(episode_means: pd.Series, seed: int, runs: int)`
- L343 `_pair_events(reference: pd.DataFrame, legacy: pd.DataFrame, candidate: pd.DataFrame)`
- L374 `_statistics(scope: dict, paired: pd.DataFrame, episodes: pd.DataFrame, doubled: pd.DataFrame)`
- L465 `_write_outputs(out_dir: Path, outputs: dict[str, pd.DataFrame], summary: dict, source: dict, dataset_sha: str)`
- L502 `run_single(scope_path: Path, runtime_dir: Path, out_dir: Path)`
- L756 `verify_replay(left: Path, right: Path)`
- L772 `main(argv=None)`

## scripts/run_sector_panic_repair_quality_historical.py

[打开文件](../../scripts/run_sector_panic_repair_quality_historical.py)

- L151 `parse_args(argv=None)`
- L163 `_workspace_path(relative: str)`
- L172 `_deep_merge(base: dict, override: dict)`
- L182 `_load_scope(path: Path)`
- L217 `_validate_runtime(runtime: Path, scope: dict)`
- L231 `_read_locked_outputs(root: Path, lock: dict, names: tuple[str, ...])`
- L254 `_quality_policy(scope: dict)`
- L271 `_adaptive_policy(scope: dict)`
- L283 `_reidentify_source(frame: pd.DataFrame, source_rule: str, target_rule: str)`
- L288 `_event_context(frame: pd.DataFrame, source_events: pd.DataFrame)`
- L301 `_pair_events(events: pd.DataFrame)`
- L356 `_comparison_statistics(paired: pd.DataFrame, episodes: pd.DataFrame, *, layer: str, candidate: str, reference: str, valid_column: str, uplift_column: str, doubled: pd.DataFrame, scope: dict)`
- L445 `_canonical(name: str, frame: pd.DataFrame)`
- L453 `_json_safe(value)`
- L465 `_bool_column(frame: pd.DataFrame, column: str)`
- L471 `_atomic_csv(path: Path, name: str, frame: pd.DataFrame)`
- L491 `_write_outputs(out_dir: Path, outputs: dict[str, pd.DataFrame], summary: dict, sources: dict, dataset_sha: str, json_outputs: dict[str, dict] | None=None)`
- L545 `_baseline_frames(source: dict[str, pd.DataFrame])`
- L563 `_normalized_frame_bytes(name: str, frame: pd.DataFrame)`
- L570 `_normalized_frame(name: str, frame: pd.DataFrame)`
- L585 `_replay_mismatch_classification(ledger_name: str, difference_field: str)`
- L606 `_baseline_replay_mismatch_details(expected: dict[str, list[pd.DataFrame]], observed: dict[str, pd.DataFrame], rule_id: str)`
- L664 `_same_replay_value(left: object, right: object)`
- L672 `_baseline_replay_mismatch_count(expected: dict[str, list[pd.DataFrame]], observed: dict[str, pd.DataFrame], rule_id: str)`
- L680 `_add_result(target: dict[str, list[pd.DataFrame]], result: dict[str, pd.DataFrame])`
- L695 `run_single(scope_path: Path, runtime_dir: Path, e2_source_root: Path, natr_source_root: Path, out_dir: Path)`
- L1307 `verify_replay(left: Path, right: Path)`
- L1327 `main(argv=None)`

## scripts/run_sector_panic_t0_cluster_duration_predictor.py

[打开文件](../../scripts/run_sector_panic_t0_cluster_duration_predictor.py)

- L63 `parse_args(argv=None)`
- L76 `_json_safe(value)`
- L88 `_read_table(root: Path, name: str)`
- L96 `_load_scope(path: Path)`
- L112 `_forbid_frozen_outputs(out_root: Path)`
- L127 `_atomic_csv(path: Path, frame: pd.DataFrame, keys: list[str])`
- L138 `_atomic_json(path: Path, payload: dict)`
- L147 `_prepare_sector_inputs(runtime_dir: Path, parent: dict, sectors: list[str], calendar: np.ndarray)`
- L199 `_path_frame(events: pd.DataFrame, selection: pd.DataFrame, packed: dict, calendar: np.ndarray)`
- L220 `run_single(scope: dict, runtime_dir: Path, events_dir: Path, signal_dir: Path, parent: dict, out_dir: Path)`
- L343 `main(argv=None)`

## scripts/run_sector_panic_v10_action_value_r1.py

[打开文件](../../scripts/run_sector_panic_v10_action_value_r1.py)

- L58 `_json_safe(value)`
- L72 `_workspace_path(relative: str | Path)`
- L78 `_forbid_frozen_writes(out_root: Path)`
- L96 `_load_yaml(path: Path)`
- L100 `_write_yaml(path: Path, payload: dict)`
- L107 `_read_csv(path: Path)`
- L111 `_verify_locked_hashes(scope: dict, *, require_impl_hashes: bool)`
- L134 `_dependency_snapshot()`
- L151 `load_scope(path: Path, *, require_frozen: bool=False, require_impl_hashes: bool=False)`
- L174 `_blocks_from_scope(scope: dict)`
- L188 `_validate_run_id(run_id: str)`
- L201 `_assert_under_experiment_root(path: Path, root: Path)`
- L214 `_output_run_dir(scope: dict, run_id: str | None=None)`
- L224 `_assert_labels_complete(labels: pd.DataFrame, expected_n: int)`
- L251 `_assert_arm_books(*, arms: dict, formal: dict, parent_rule_id: str, cost_mode: str)`
- L283 `_frame_equal_exact(left: pd.DataFrame, right: pd.DataFrame, columns: list[str])`
- L307 `_load_v10_tables(scope: dict)`
- L319 `_load_runtime(scope: dict, runtime_dir: Path)`
- L328 `_build_panels(tables: dict, parent: pd.DataFrame, calendar: np.ndarray)`
- L334 `_bool_series(frame: pd.DataFrame, column: str)`
- L342 `build_dataset(scope: dict, runtime_dir: Path)`
- L457 `cmd_preflight(scope_path: Path, runtime_dir: Path, out_root: Path | None)`
- L546 `cmd_freeze(scope_path: Path)`
- L609 `_evaluate_gates(*, scope: dict, paired: dict[str, pd.DataFrame], block_paired: dict[str, dict[str, pd.DataFrame]], diagnostics: dict, double_paired: dict[str, pd.DataFrame], loo: pd.DataFrame, bootstrap_p3_p0: tuple[float, float, float], bootstrap_p3_p2: tuple[float, float, float])`
- L776 `cmd_run(scope_path: Path, runtime_a: Path, runtime_b: Path, run_id: str | None=None)`
- L1256 `_render_report(summary: dict, gate: dict, diagnostics: dict, paired: dict, scope: dict)`
- L1292 `cmd_report(run_dir: Path)`
- L1302 `parse_args(argv=None)`
- L1325 `main(argv=None)`

## scripts/run_sector_panic_v10_delayed_structure_path_check.py

[打开文件](../../scripts/run_sector_panic_v10_delayed_structure_path_check.py)

- L49 `_json_safe(value)`
- L63 `_workspace_path(relative: str | Path)`
- L69 `_read_csv(path: Path)`
- L73 `_forbid_frozen_writes(out_root: Path)`
- L86 `_verify_locked_hashes(scope: dict)`
- L106 `load_scope(path: Path)`
- L125 `_load_tables(scope: dict)`
- L137 `_load_runtime(scope: dict, runtime_dir: Path)`
- L148 `_build_panels(tables: dict, parent: pd.DataFrame, calendar: np.ndarray)`
- L154 `_bool_series(frame: pd.DataFrame, column: str)`
- L162 `_output_dir(scope: dict, run_id: str)`
- L174 `_render_report(summary: dict, gates: dict)`
- L208 `run(scope_path: Path, runtime_dir: Path, run_id: str)`
- L322 `parse_args(argv=None)`
- L334 `main(argv=None)`

## scripts/run_sector_panic_v10_h1_mech_half.py

[打开文件](../../scripts/run_sector_panic_v10_h1_mech_half.py)

- L46 `_json_safe(value)`
- L58 `parse_args(argv=None)`
- L70 `_workspace_path(relative: str)`
- L76 `_load_scope(path: Path)`
- L94 `_forbid_frozen(out_root: Path)`
- L111 `_read_locked_v10(source: Path, scope: dict)`
- L130 `_metrics(candidate: pd.DataFrame, control: pd.DataFrame)`
- L151 `_late_time_order(trigger: pd.DataFrame, components: pd.DataFrame, v12_daily: pd.DataFrame, start: int)`
- L173 `run_single(scope_path: Path, runtime_dir: Path, v10_source: Path, v12_daily_path: Path, out_dir: Path)`
- L284 `main(argv=None)`

## scripts/run_sector_panic_v12_evidence_stack_engine.py

[打开文件](../../scripts/run_sector_panic_v12_evidence_stack_engine.py)

- L52 `_json_safe(value)`
- L64 `_workspace_path(relative: str)`
- L70 `_forbid_frozen_outputs(out_root: Path)`
- L83 `parse_args(argv=None)`
- L95 `_load_scope(path: Path)`
- L116 `_concat(frames)`
- L121 `_simulate_v12(*, stock, policies, panels, calendar, boundaries, rule_id, policy)`
- L144 `_bootstrap(pair: pd.DataFrame, *, seed: int, runs: int)`
- L166 `_event_stats(arm: pd.DataFrame, control: pd.DataFrame, scope: dict)`
- L211 `_gates(scope, normal, doubled, retention, replay_ok)`
- L240 `_validate_v10_control(frozen_v10: dict)`
- L253 `_summary_report(summary: dict, gates: pd.DataFrame)`
- L288 `run_single(scope_path, runtime_dir, r7_source, v10_source, out_dir)`
- L400 `main(argv=None)`

## scripts/run_sector_panic_v12_evidence_stack_engine_r1.py

[打开文件](../../scripts/run_sector_panic_v12_evidence_stack_engine_r1.py)

- L175 `class R1ReplayError`
- L179 `_json_safe(value)`
- L193 `_canonical_json(value: object)`
- L202 `_strict_bool(mapping: Mapping, field: str, expected: bool, section: str)`
- L209 `_workspace_path(value: object, *, field: str)`
- L220 `_hash_lock(item: object, *, name: str)`
- L235 `_read_yaml(path: Path, *, label: str)`
- L247 `_load_scope(path: Path)`
- L343 `_safe_output_root(scope: dict, requested: Path)`
- L373 `_concat(frames: Iterable[pd.DataFrame])`
- L378 `_simulate_r1(*, stock: pd.DataFrame, policies: pd.DataFrame, panels: dict, calendar: Iterable[int], boundaries: dict, rule_id: str, policy, enable_v12: bool)`
- L416 `_read_manifest_output(root: Path, manifest: dict, name: str)`
- L435 `_normalize_object_missing(frame: pd.DataFrame)`
- L445 `_normalised_equal(left: pd.DataFrame, right: pd.DataFrame, *, frame_name: str)`
- L505 `_event_books(result: dict[str, pd.DataFrame], *, event_episode: pd.DataFrame, calendar: Iterable[int], validate: bool)`
- L542 `_filter_rule(frame: pd.DataFrame, rule_id: str, *, name: str)`
- L551 `_validate_baseline_replay(*, control: dict[str, pd.DataFrame], control_events: pd.DataFrame, frozen_root: Path, frozen_manifest: dict, rule_id: str)`
- L582 `_validate_source_support(stock: pd.DataFrame, event_episode: pd.DataFrame, scope: dict)`
- L614 `_event_stats(arm: pd.DataFrame, control: pd.DataFrame, scope: dict)`
- L705 `_winner_damage(frozen_components: pd.DataFrame, r1_components: pd.DataFrame)`
- L768 `_integrity_metrics(*, normal: dict[str, pd.DataFrame], doubled: dict[str, pd.DataFrame], baseline_replay_match: bool, runtime_a_b_byte_equal: bool)`
- L820 `_gates(scope: dict, normal: dict, doubled: dict, retention: dict, integrity: dict)`
- L958 `_metric_subset(metrics: dict, fields: Iterable[str])`
- L962 `_build_summary(*, scope: dict, gates: pd.DataFrame, normal_metrics: dict, double_metrics: dict, retention: dict, damage: dict, normal_components: pd.DataFrame, normal_events: pd.DataFrame)`
- L1033 `_canonical_frame(frame: pd.DataFrame)`
- L1056 `_write_frame(path: Path, frame: pd.DataFrame)`
- L1066 `_write_core(stage: Path, outputs: dict[str, pd.DataFrame])`
- L1075 `_file_metadata(root: Path, names: Iterable[str])`
- L1093 `_manifest(*, scope: dict, scope_path: Path, runtime_inputs: dict, outputs: dict, integrity: dict)`
- L1119 `_runtime_lock_name(runtime_name: str)`
- L1125 `_assert_locked_runtime_path(runtime_dir: Path, runtime_name: str, v10_scope: dict)`
- L1136 `_prepare_runtime(*, scope: dict, v10_scope: dict, runtime_dir: Path, runtime_name: str, r7_source: Path, v10_source: Path)`
- L1326 `_same_runtime_analysis(first: dict, second: dict)`
- L1338 `run_replay_bundle(*, scope_path: Path=DEFAULT_SCOPE, runtime_a: Path=DEFAULT_RUNTIME_A, runtime_b: Path=DEFAULT_RUNTIME_B, r7_source: Path=DEFAULT_R7_SOURCE, v10_source: Path=DEFAULT_V10_SOURCE, out_root: Path=DEFAULT_OUTPUT)`
- L1467 `parse_args(argv=None)`
- L1483 `main(argv=None)`

## scripts/run_sector_panic_v12_r1.py

[打开文件](../../scripts/run_sector_panic_v12_r1.py)

- L31 `class V13PreflightError`
- L35 `parse_args(argv: list[str] | None=None)`
- L51 `_workspace_input(path: Path, *, field: str)`
- L62 `_calendar_boundary(path: Path, freeze_date: int)`
- L73 `preflight(scope_path: str | Path=DEFAULT_SCOPE, *, calendar_path: str | Path | None=None)`
- L107 `main(argv: list[str] | None=None)`

## scripts/run_sector_panic_v14_forward.py

[打开文件](../../scripts/run_sector_panic_v14_forward.py)

- L41 `class V14PreflightError`
- L45 `parse_args(argv: list[str] | None=None)`
- L61 `_workspace_input(path: Path, *, field: str)`
- L72 `simulate_v10_and_v14_component(**kwargs)`
- L93 `preflight(scope_path: str | Path=DEFAULT_SCOPE, *, calendar_path: str | Path | None=None)`
- L138 `main(argv: list[str] | None=None)`

## scripts/run_vehicle_compare.py

[打开文件](../../scripts/run_vehicle_compare.py)

- L37 `_adj_only(adj: pd.DataFrame)`
- L45 `_index_bars(code: str)`
- L62 `_load_basket_weights(path: Path)`
- L77 `_replica_on_dates(iw: pd.DataFrame, dates: list[int])`
- L81 `_trade_dates_in(start: int, end: int)`
- L103 `resolve_expected_trade_dates(start: int | None, end: int | None)`
- L115 `_load_nav(path: Path)`
- L129 `_resolve_basket(rel: str)`
- L139 `run_weight_book(item: dict, prices: pd.DataFrame)`
- L263 `run_pharma_events(item: dict, prices: pd.DataFrame)`
- L357 `_fmt(block: dict | None, key: str)`
- L377 `main()`

## scripts/sector_panic_hold_sensitivity.py

[打开文件](../../scripts/sector_panic_hold_sensitivity.py)

- L134 `_same_root_contract(existing: dict, requested: dict)`
- L138 `_same_grid_identity(existing: dict, requested: dict)`
- L148 `_output_snapshot_ok(manifest: dict, arm_dir: Path)`
- L169 `_study_config_snapshot_ok(manifest: dict, sector: str, hold: int, baseline_raw: dict)`
- L200 `_legacy_arm_safe_to_upgrade(manifest: dict, arm_dir: Path, sector: str, hold: int, baseline_raw: dict)`
- L238 `_manifest_snapshot_ok(manifest: dict, arm_dir: Path, hold: int, baseline_hash: str, end_date: int, runtime_hash: str, runtime_dataset_hash: str | None=None, baseline_raw: dict | None=None, sector: str | None=None)`
- L274 `_patch_arm_manifest(manifest_path: Path, hold: int, baseline_hash: str, end_date: int, runtime_hash: str, runtime_dataset_hash: str)`
- L306 `_write_study_config(sector: str, hold: int, raw: dict)`
- L319 `_compare_formal_20d(sector: str, hold: int)`
- L375 `run_arm(sector: str, hold: int, end_date: int, runtime_snapshot: VerifiedRuntimeSnapshot | str)`
- L464 `main()`

## scripts/sleeve_factor_attribution.py

[打开文件](../../scripts/sleeve_factor_attribution.py)

- L33 `_pct(value: Any, digits: int=1)`
- L39 `_num(value: Any, digits: int=2)`
- L45 `_compound(series: pd.Series)`
- L52 `_annualized_return(period_returns: pd.Series)`
- L59 `_information_ratio(returns: pd.Series)`
- L69 `_max_drawdown(period_returns: pd.Series)`
- L78 `_read_year_partitions(dataset: str, years: set[int], columns: list[str])`
- L89 `_next_trade_date(trade_dates: list[int], date: int)`
- L96 `_load_phase2_row(runs_csv: Path, case: str)`
- L104 `_find_value_col(df: pd.DataFrame, name: str)`
- L114 `_load_index_returns(periods: pd.DataFrame)`
- L142 `_fast_backtest_scores(scores: pd.DataFrame, start: str, end: str, top_n: int, score_col: str='composite_score')`
- L223 `_summarise_periods(name: str, periods: pd.DataFrame, group: str)`
- L247 `_monthly_wide(periods_by_name: dict[str, pd.DataFrame])`
- L269 `_realised_factor_ic(factor_name: str, factor_df: pd.DataFrame, fwd_rets: pd.DataFrame, start: str, end: str, horizon: int, min_stocks: int=30)`
- L327 `_build_sleeve_scores(cfg_path: Path, start: str, end: str, out_dir: Path, force_rebuild: bool)`
- L430 `_load_final_composite(out_dir: Path)`
- L443 `_factor_score_panel(factor_name: str, factor_df: pd.DataFrame, sign: float=1.0)`
- L452 `_write_report(out_doc: Path, meta: dict[str, Any], sleeve_summary: pd.DataFrame, factor_summary: pd.DataFrame, factor_ic: pd.DataFrame, monthly: pd.DataFrame)`
- L541 `main()`

## scripts/sleeve_weight_cross_year.py

[打开文件](../../scripts/sleeve_weight_cross_year.py)

- L41 `_pct(value: Any, digits: int=1)`
- L47 `_num(value: Any, digits: int=3)`
- L53 `_read_csv(path: Path)`
- L59 `_run_one(year: int, start: str, end: str, config_path: Path, out_root: Path, top_n: int, skip_existing: bool)`
- L111 `_extract_year_summary(year: int, year_dir: Path)`
- L201 `_write_report(summary: pd.DataFrame, out_doc: Path)`
- L308 `main()`

## scripts/sleeve_weight_diagnostics.py

[打开文件](../../scripts/sleeve_weight_diagnostics.py)

- L48 `_load_config(path: Path)`
- L52 `_signal_dates_from_aligned(aligned: dict[str, pd.DataFrame])`
- L60 `_sleeve_factors(config: dict[str, Any])`
- L72 `_eligible_names_for_date(factor_dfs: dict[str, pd.DataFrame], fwd_rets: pd.DataFrame, signal_date: int, composite_cfg: dict[str, Any], trade_dates: list[int], expected_dates: list[int])`
- L106 `_ic_stats_for_factor(icw: ICWeighting, ic_df: pd.DataFrame, signal_date: int, factor_name: str, trade_dates: list[int])`
- L173 `_compute_weight_rows(config: dict[str, Any], aligned: dict[str, pd.DataFrame], fwd_rets: pd.DataFrame, signal_dates: list[int], analysis_start: int, analysis_end: int)`
- L249 `_summarise_weights(weight_rows: pd.DataFrame)`
- L281 `_monthly_weight_summary(weight_rows: pd.DataFrame)`
- L300 `_selection_exposure_rows(config: dict[str, Any], sleeve_scores: dict[str, pd.DataFrame], aligned: dict[str, pd.DataFrame], analysis_start: int, analysis_end: int, top_n: int)`
- L362 `_summarise_exposure(exposures: pd.DataFrame)`
- L385 `_find_phase1_log(start: str)`
- L397 `_parse_phase1_log(path: Path | None)`
- L419 `_reconcile_ic(phase1_log: Path | None, factor_ic_path: Path, factor_top_bottom_path: Path)`
- L481 `_factor_to_sleeves(config: dict[str, Any])`
- L489 `_compute_factor_diagnostics(aligned: dict[str, pd.DataFrame], fwd_rets: pd.DataFrame, config: dict[str, Any], start: str, end: str, horizon: int, top_n: int)`
- L536 `_fmt_float(value: Any, digits: int=3)`
- L542 `_write_report(out_doc: Path, meta: dict[str, Any], weight_summary: pd.DataFrame, exposure_summary: pd.DataFrame, ic_reconcile: pd.DataFrame, factor_top_bottom: pd.DataFrame)`
- L706 `main()`

## scripts/strategy_alpha_failure_diagnosis.py

[打开文件](../../scripts/strategy_alpha_failure_diagnosis.py)

- L76 `_resolve_path(path: str | Path)`
- L81 `_pct(value: Any, digits: int=1)`
- L87 `_num(value: Any, digits: int=3)`
- L93 `_compound(series: pd.Series)`
- L100 `_annualize_from_period_returns(period_returns: pd.Series, periods_per_year: int=52)`
- L110 `_sharpe_from_period_returns(period_returns: pd.Series, periods_per_year: int=52)`
- L117 `_max_drawdown(period_returns: pd.Series)`
- L127 `_ir_from_excess(period_returns: pd.Series, benchmark_returns: pd.Series)`
- L137 `_idxmax_label(series: pd.Series)`
- L142 `_read_json(path: Path)`
- L151 `_read_parquet_safe(path: Path)`
- L155 `_read_csv_safe(path: Path)`
- L162 `_load_runs(path: Path)`
- L177 `_load_period_data(row: pd.Series)`
- L197 `_load_all_periods(runs: pd.DataFrame)`
- L208 `_common_calendar_evaluation(runs: pd.DataFrame, period_data: dict[tuple, dict[str, Any]])`
- L380 `_compute_investment_gate(normalized: pd.DataFrame, runs: pd.DataFrame, calendar_audit: pd.DataFrame)`
- L498 `_build_factor_scorecard(period_data: dict[tuple, dict[str, Any]], runs: pd.DataFrame)`
- L664 `_build_sleeve_scorecard(period_data: dict[tuple, dict[str, Any]], runs: pd.DataFrame)`
- L708 `_build_construction_diagnostics(period_data: dict[tuple, dict[str, Any]], runs: pd.DataFrame, out_dir: Path)`
- L793 `_build_regime_router_scorecard(period_data: dict[tuple, dict[str, Any]], runs: pd.DataFrame)`
- L849 `_build_router_opportunity_cost(period_data: dict[tuple, dict[str, Any]], runs: pd.DataFrame, out_dir: Path)`
- L1133 `_check_artifact_consistency(out_dir: Path, out_doc: Path, out_go_nogo: Path)`
- L1168 `_write_alpha_failure_report(out_doc: Path, normalized: pd.DataFrame, calendar_audit: pd.DataFrame, investment_gate: pd.DataFrame, factor_scorecard: pd.DataFrame, sleeve_scorecard: pd.DataFrame, construction_bridge: pd.DataFrame, pre_post_cost: pd.DataFrame, regime_router: pd.DataFrame, opportunity_cost: pd.DataFrame, oracle_df: pd.DataFrame, pred_df: pd.DataFrame)`
- L1449 `_write_go_nogo_report(out_doc: Path, investment_gate: pd.DataFrame, normalized: pd.DataFrame, calendar_audit: pd.DataFrame)`
- L1545 `main()`

## scripts/test_v10_coconfirmation_gate.py

[打开文件](../../scripts/test_v10_coconfirmation_gate.py)

- L32 `load()`
- L51 `verify_identity(ev: pd.DataFrame, cr: pd.DataFrame)`
- L64 `rank_edge(cr: pd.DataFrame)`
- L85 `co_confirmation_gate(ev: pd.DataFrame, cr: pd.DataFrame)`
- L97 `evaluate(ev: pd.DataFrame, c: pd.DataFrame)`
- L162 `main()`

## scripts/validate_factor_quality_outputs.py

[打开文件](../../scripts/validate_factor_quality_outputs.py)

- L54 `load_config(config_path: Optional[Path])`
- L60 `check_files_exist(out_dir: Path)`
- L70 `check_csvs_readable(out_dir: Path)`
- L98 `check_no_stub(out_dir: Path)`
- L113 `check_neutralization_validity(out_dir: Path, config: dict)`
- L139 `check_gate_neutralization_consistency(out_dir: Path, config: dict)`
- L181 `check_capacity_cny_scale(out_dir: Path, config: dict)`
- L226 `check_capacity_participation(out_dir: Path)`
- L253 `check_candidate_pool_contract(out_dir: Path, config: dict=None)`
- L325 `check_run_manifest(out_dir: Path, config_path: Optional[Path]=None)`
- L386 `check_diagnostic_csvs_in_run_dir(out_dir: Path)`
- L408 `check_no_diagnostic_csvs_in_root(out_dir: Path)`
- L420 `check_output_freshness(out_dir: Path, max_age_minutes: int=120)`
- L445 `main()`

## scripts/validate_market_state_momentum_rules.py

[打开文件](../../scripts/validate_market_state_momentum_rules.py)

- L107 `_load_factor_cache(factor_name: str)`
- L162 `_load_fwd_returns()`
- L195 `_load_index_daily(index_code: str, start: str, end: str)`
- L211 `_load_index_cache_fast(index_code: str)`
- L241 `_build_regime_features_pit(index_df: pd.DataFrame, prices_df: Optional[pd.DataFrame], signal_dates: np.ndarray)`
- L268 `_build_simplified_features_pit(index_df: pd.DataFrame, signal_dates: np.ndarray)`
- L329 `_rank_ic(factor_vals: pd.Series, fwd_rets: pd.Series, min_obs: int=30)`
- L341 `_compute_factor_ic_series(factor_df: pd.DataFrame, fwd_df: pd.DataFrame, horizon: str='fwd_ret_20d')`
- L366 `_compute_rolling_q75(state_series: pd.Series, dates: np.ndarray, min_warmup: int=MIN_PIT_WARMUP)`
- L390 `apply_market_state_rules(panel: pd.DataFrame, mode: str='rolling_pit', vol_q75_research: Optional[float]=None, breadth_q75_research: Optional[float]=None)`
- L474 `apply_market_state_rules_oos(train_panel: pd.DataFrame, test_panel: pd.DataFrame, requested_train_end: Optional[int]=None)`
- L552 `_compute_walkforward_validation(panel: pd.DataFrame, daily_ic: pd.DataFrame, train_end_dates: List[int])`
- L721 `_discover_rules_from_train_window(train_panel: pd.DataFrame, factor_ics: Dict[str, pd.DataFrame], factor_data: Dict[str, pd.DataFrame], fwd_df: pd.DataFrame)`
- L860 `_translate_rules_to_test_signals(rules: List[Dict[str, Any]], train_panel: pd.DataFrame, test_panel: pd.DataFrame)`
- L962 `_compute_window_verdict(test_signals: pd.DataFrame, test_ic: pd.DataFrame, discovered_rules: List[Dict[str, Any]])`
- L1044 `_compute_overall_discovery_verdict(window_results: List[Dict[str, Any]], all_test_signals: pd.DataFrame, all_test_ic: pd.DataFrame)`
- L1173 `_compute_walkforward_discovery_validation(regime_features: pd.DataFrame, factor_ics: Dict[str, pd.DataFrame], factor_data: Dict[str, pd.DataFrame], fwd_df: pd.DataFrame, ic_series: pd.DataFrame, train_end_dates: List[int], horizon_col: str)`
- L1331 `_compute_label_metrics(ic_by_label: pd.Series, label: str)`
- L1409 `_compute_validation_metrics(rule_signals: pd.DataFrame, daily_ic: pd.DataFrame)`
- L1581 `_compute_validation_by_year(rule_signals: pd.DataFrame, daily_ic: pd.DataFrame)`
- L1622 `_resolve_final_verdict(validation_results: Dict[str, Any], walkforward_results: Optional[Dict[str, Any]]=None, is_oos: bool=False)`
- L1702 `_write_outputs(out_dir: Path, run_id: str, args, rule_signals: pd.DataFrame, daily_ic: pd.DataFrame, validation_results: Dict[str, Any], validation_by_year: pd.DataFrame, mode: str, vol_q75: Optional[float], breadth_q75: Optional[float], frozen_thresholds: Optional[Dict[str, Any]]=None, walkforward_results: Optional[Dict[str, Any]]=None)`
- L1954 `_write_discovery_outputs(out_dir: Path, walkforward_results: Dict[str, Any], validation_results: Dict[str, Any])`
- L2092 `_write_validation_report(out_dir: Path, run_id: str, args, validation_results: Dict[str, Any], validation_by_year: pd.DataFrame, mode: str, vol_q75: Optional[float], breadth_q75: Optional[float], rule_signals: pd.DataFrame, frozen_thresholds: Optional[Dict[str, Any]]=None, walkforward_results: Optional[Dict[str, Any]]=None)`
- L2436 `main()`

## scripts/validate_photoresist_panic_thresholds.py

[打开文件](../../scripts/validate_photoresist_panic_thresholds.py)

- L46 `parse_args()`
- L58 `load_yaml(path: Path)`
- L63 `load_validation_inputs(input_dir: Path)`
- L80 `_ensure_return_column(frame: pd.DataFrame, window: int)`
- L90 `build_threshold_gate(core_basket: pd.DataFrame, gate_id: str, gate_config: dict)`
- L123 `cluster_threshold_events(gated: pd.DataFrame, calendar: np.ndarray, max_gap: int)`
- L159 `compute_market_regime(index_prices: pd.DataFrame, config: dict)`
- L183 `summarize_index_coverage(index_prices: pd.DataFrame, index_codes: list[str], target_dates: pd.Series)`
- L207 `attach_event_diagnostics(events: pd.DataFrame, core_basket: pd.DataFrame, market_regime: pd.DataFrame, calendar: np.ndarray, volume_config: dict)`
- L260 `assign_sample_split(event_date: int, split_config: dict)`
- L267 `summarize_gate(gate_id: str, gate_config: dict, forward_returns: pd.DataFrame, cost_bps: int, events: pd.DataFrame | None=None)`
- L296 `summarize_groups(forward_returns: pd.DataFrame, group_columns: list[str], cost_bps: int)`
- L320 `build_candidate_forward_returns(core_basket: pd.DataFrame, index_prices: pd.DataFrame, calendar: np.ndarray, market_regime: pd.DataFrame)`
- L347 `_event_exclusion_dates(events: pd.DataFrame, calendar: np.ndarray, buffer_days: int)`
- L361 `run_placebo_tests(gate_id: str, real_returns: pd.DataFrame, candidate_returns: pd.DataFrame, calendar: np.ndarray, config: dict, random_seed: int)`
- L424 `run_bootstrap_tests(gate_id: str, forward_returns: pd.DataFrame, config: dict, random_seed: int, cost_bps: int)`
- L460 `evaluate_threshold_acceptance(gate_summary: pd.DataFrame, market_summary: pd.DataFrame, placebo: pd.DataFrame, bootstrap: pd.DataFrame, basket_loo: pd.DataFrame, base_go_nogo: dict, validation_config: dict)`
- L552 `_markdown_table(frame: pd.DataFrame)`
- L561 `generate_report(gate_summary: pd.DataFrame, market_summary: pd.DataFrame, volume_summary: pd.DataFrame, sample_summary: pd.DataFrame, placebo: pd.DataFrame, bootstrap: pd.DataFrame, top1_summary: pd.DataFrame, top1_market_summary: pd.DataFrame, top1_concentration: pd.DataFrame, top1_loo: pd.DataFrame, acceptance: dict)`
- L607 `main()`

## scripts/validate_validation_manifest.py

[打开文件](../../scripts/validate_validation_manifest.py)

- L60 `sha256_hex(path: Path)`
- L65 `load_runs(runs_path: Path, require_sample: bool=False)`
- L99 `validate_year_coverage(df: 'pd.DataFrame', required_validation_years: List[int], required_ytd_years: List[int])`
- L123 `validate_year_coverage_multi(df: 'pd.DataFrame', strategy_configs: dict, required_validation_years: List[int], required_ytd_years: List[int])`
- L169 `validate_return_codes(df: 'pd.DataFrame')`
- L181 `validate_strategy_unique(df: 'pd.DataFrame')`
- L194 `validate_manifests(df: 'pd.DataFrame', factors_config_sha256_expected: str, regime_config_sha256_expected: str, factors_config_relpath: str, regime_config_relpath: str)`
- L280 `_parse_strategy_configs(legacy: Optional[List[str]], entries: Optional[List[List[str]]])`
- L373 `_looks_like_windows_absolute_in_legacy(entry: str)`
- L384 `_paths_equivalent(a: str, b: str)`
- L409 `validate_manifests_multi(df: 'pd.DataFrame', strategy_configs: dict[str, tuple[Path, Path]])`
- L501 `main()`

## scripts/validation_firewall.py

[打开文件](../../scripts/validation_firewall.py)

- L28 `class FirewallSealedError`
- L34 `class TrainValidationSplit`
- L59 `TrainValidationSplit.set_threshold(self, name: str, value: Any)`
- L67 `TrainValidationSplit.validate(self, results: dict[str, Any])`
- L80 `TrainValidationSplit.is_sealed(self)`
- L85 `class ValidationFirewall`
- L96 `ValidationFirewall.add_split(self, split: TrainValidationSplit)`
- L99 `ValidationFirewall.record_rejection(self, candidate_name: str, gate_name: str, detail: str, split_name: str='')`
- L126 `ValidationFirewall.record_pass(self, candidate_name: str)`
- L138 `ValidationFirewall.summary(self)`
- L172 `_candidate_identity_hash(feature_name: str, direction: str, threshold_method: str, missing_strategy: str, code_sha256: str, config_sha256: str)`
- L192 `class CandidateRegistry`
- L200 `CandidateRegistry.__init__(self, registry_path: str)`
- L206 `CandidateRegistry._merge_status(first: str, second: str)`
- L215 `CandidateRegistry._validated_entries(payload: Any, path: str)`
- L274 `CandidateRegistry._read_disk_entries(self)`
- L287 `CandidateRegistry._pid_is_alive(pid: int)`
- L299 `CandidateRegistry._locked(self, timeout_sec: float=30.0)`
- L342 `CandidateRegistry._load(self)`
- L345 `CandidateRegistry._save(self)`
- L371 `CandidateRegistry._save_locked(self)`
- L397 `CandidateRegistry.is_sealed(self, candidate_hash: str, valid_years: list[int])`
- L427 `CandidateRegistry.untested_years(self, candidate_hash: str, valid_years: list[int])`
- L443 `CandidateRegistry.claim_validation_splits(self, candidate_hash: str, candidate_name: str, splits: list[dict], run_id: str, timeout_sec: float=30.0)`
- L507 `CandidateRegistry.n_unique_candidates(self)`
- L510 `CandidateRegistry.register(self, candidate_hash: str, candidate_name: str, status: str, validated_splits: list[dict])`
- L544 `CandidateRegistry.commit(self)`
- L555 `expanding_window_split(events_by_year: dict[int, list[str]], min_train_years: int=3)`
- L593 `leave_one_year_out_split(events_by_year: dict[int, list[str]], min_events_per_fold: int=5)`
- L636 `_hash_dict(d: dict)`
- L642 `_count_by_gate(ledger: list[dict])`

## scripts/verify_sector_panic_rebuild_mutations.py

[打开文件](../../scripts/verify_sector_panic_rebuild_mutations.py)

- L80 `_apply(root: Path, mid: str)`
- L89 `_env(env_root: Path)`
- L95 `_parse_pytest(proc: subprocess.CompletedProcess)`
- L126 `_pytest(test_id: str, env_root: Path, *, collect_only: bool=False)`
- L162 `_stage(tmp: Path)`
- L179 `main()`

## scripts/volume_features.py

[打开文件](../../scripts/volume_features.py)

- L45 `class VolumeFeatures`
- L78 `VolumeFeatures.columns()`
- L86 `_rolling_median_ratio(series: pd.Series, window: int=ROLLING_WINDOW, min_periods: int=MIN_PERIODS)`
- L98 `_robust_zscore(series: pd.Series, window: int=ROLLING_WINDOW, min_periods: int=MIN_PERIODS)`
- L119 `_amihud_illiquidity(pct_chg: pd.Series, amount: pd.Series, window: int=AMIHUD_SMOOTH_WINDOW)`
- L134 `_down_amount_share(pct_chg: pd.Series, amount: pd.Series, window: int=DOWN_DAYS_WINDOW)`
- L148 `_basket_median(values: list[float], n_components: int | None=None)`
- L160 `_basket_fraction(values: list[bool], n_components: int | None=None)`
- L168 `_cross_sectional_dispersion(values: list[float], n_components: int | None=None)`
- L186 `compute_volume_features(signal_id: str, signal_date: int, component_codes: list[str], prices: pd.DataFrame, daily_basic: pd.DataFrame | None=None, limit_status: pd.DataFrame | None=None)`

## sector_panic/__init__.py

[打开文件](../../sector_panic/__init__.py)

无顶层函数/类；阅读模块常量、导入或入口逻辑。

## sector_panic/backtest.py

[打开文件](../../sector_panic/backtest.py)

- L19 `build_pit_universe_from_weights(weights: pd.DataFrame, index_code: str, calendar: np.ndarray)`
- L103 `active_codes(universe: pd.DataFrame, trade_date: int)`
- L114 `build_signal_frame(basket_daily: pd.DataFrame, sector_index: pd.DataFrame, parent_index: pd.DataFrame, gate_config: dict)`
- L205 `cluster_first_triggers(signal_frame: pd.DataFrame, calendar: np.ndarray, max_gap_trading_days: int=5)`
- L244 `parse_second_breakout(returns: np.ndarray, dates: np.ndarray, observation_horizon: int=60)`
- L307 `build_frozen_path(prices: pd.DataFrame, codes: list[str], entry_date: int, calendar: np.ndarray, horizon: int, suspended_keys: set[tuple[str, int]] | None=None)`
- L360 `class RuleResult`
- L372 `_date_position(dates: np.ndarray, trade_date: int)`
- L379 `simulate_rule(rule_id: str, returns: np.ndarray, dates: np.ndarray, hold_days: int, stop_levels: list[float], round_trip_bps: int, boundary_exit_date: int | None=None, executable_exit=None)`
- L483 `assign_sample_split(trade_date: int, sample_split: dict)`
- L495 `summarize_trade_ledger(ledger: pd.DataFrame, primary_cost_bps: int)`
- L552 `annual_trade_returns(ledger: pd.DataFrame, primary_cost_bps: int)`

## sector_panic/component_avwap_loss_audit.py

[打开文件](../../sector_panic/component_avwap_loss_audit.py)

- L27 `class LossAuditPolicy`
- L31 `LossAuditPolicy.__post_init__(self)`
- L38 `_number(value)`
- L46 `_optional_date(value)`
- L51 `_require_columns(frame: pd.DataFrame, columns: set[str], name: str)`
- L57 `_require_unique(frame: pd.DataFrame, keys: list[str], name: str)`
- L62 `build_event_boundaries(events: pd.DataFrame, calendar: Iterable[int], maximum_holding_sessions: int=20)`
- L105 `prepare_market_path(prices: pd.DataFrame, suspended_keys: set[tuple[str, int]], code: str, dates: Iterable[int])`
- L178 `analyze_component_path(path: pd.DataFrame, entry_date: int, actual_sale_date: int, causal_boundary_date: int, entry_price: float, actual_sale_price: float)`
- L331 `classify_exit_group(reason: str, net_return: float, avwap_arm_date: int | None)`
- L343 `build_component_loss_ledger(diagnostics: pd.DataFrame, attempts: pd.DataFrame, inventory: pd.DataFrame, event_ledger: pd.DataFrame, prices: pd.DataFrame, suspended_keys: set[tuple[str, int]], calendar: Iterable[int], policy: LossAuditPolicy=LossAuditPolicy())`
- L518 `_group_summary(group: pd.DataFrame, total_pnl: float, total_loss: float)`
- L546 `build_pnl_breakdown(ledger: pd.DataFrame)`
- L574 `build_post_exit_state_summary(ledger: pd.DataFrame)`
- L598 `build_loss_concentration(ledger: pd.DataFrame)`
- L631 `build_audit_outputs(diagnostics: pd.DataFrame, attempts: pd.DataFrame, inventory: pd.DataFrame, event_ledger: pd.DataFrame, prices: pd.DataFrame, suspended_keys: set[tuple[str, int]], calendar: Iterable[int], policy: LossAuditPolicy=LossAuditPolicy())`

## sector_panic/component_entry_avwap_gate.py

[打开文件](../../sector_panic/component_entry_avwap_gate.py)

- L35 `_require(frame: pd.DataFrame, columns: set[str], label: str)`
- L41 `_rename_rule(frame: pd.DataFrame, old: str, new: str, batch: str)`
- L56 `_path_avwap(lookup: pd.DataFrame, code: str, dates: np.ndarray)`
- L103 `build_signal_avwap_gate(selection: pd.DataFrame, panel: pd.DataFrame, calendar: Iterable[int], signal_date: int, observation_date: int, normalized_event_capital: float=1.0)`
- L165 `_empty_cash_event(sector: str, event_id: str, signal_date: int, entry_date: int, selected_count: int, gate: pd.DataFrame, rule_id: str=ENTRY_GATE_RULE_ID, revision_batch_id: str='ENTRY_AVWAP_FORWARD')`
- L210 `simulate_gated_avwap_event(sector: str, event_id: str, signal_date: int, gate_observation_date: int, entry_date: int, selection: pd.DataFrame, panel: pd.DataFrame, calendar: Iterable[int], policy: ComponentPolicy, next_event_entry_date: int | None=None, component_exit_rule: str=COMPONENT_R4_AVWAP, output_rule_id: str=ENTRY_GATE_RULE_ID, revision_batch_id: str='ENTRY_AVWAP_FORWARD')`

## sector_panic/component_exit.py

[打开文件](../../sector_panic/component_exit.py)

- L31 `class ComponentPolicy`
- L50 `_required_panel(panel: pd.DataFrame)`
- L67 `_avwap_ready(lookup: pd.DataFrame)`
- L71 `_avwap_state(lookup: pd.DataFrame, code: str, entry_pos: int, current_pos: int, dates: np.ndarray)`
- L98 `compute_natr20(panel: pd.DataFrame, code: str, signal_date: int, lookback_sessions: int=20)`
- L114 `_compute_natr_from_lookup(lookup: pd.DataFrame, code: str, signal_date: int, lookback_sessions: int, date_values: np.ndarray)`
- L144 `add_natr_to_selection(selection: pd.DataFrame, panel: pd.DataFrame, signal_date: int, policy: ComponentPolicy)`
- L178 `_component_path(lookup: pd.DataFrame, code: str, entry_date: int, dates: np.ndarray, entry_price: float)`
- L199 `_component_result(sector: str, event_id: str, signal_date: int, entry_date: int, code: str, rule_id: str, selected_count: int, item: dict, lookup: pd.DataFrame, calendar: np.ndarray, policy: ComponentPolicy, next_event_entry_date: int | None)`
- L509 `simulate_component_event(sector: str, event_id: str, signal_date: int, entry_date: int, selection: pd.DataFrame, panel: pd.DataFrame, calendar: Iterable[int], rule_id: str, policy: ComponentPolicy, next_event_entry_date: int | None=None)`
- L646 `execute_paired_component_event(*args, candidate_rule: str=COMPONENT_R4, **kwargs)`

## sector_panic/component_natr_stop.py

[打开文件](../../sector_panic/component_natr_stop.py)

- L38 `class AdaptiveStopPolicy`
- L47 `AdaptiveStopPolicy.validate(self)`
- L62 `cost_adjusted_loss_distance(stop_distance: float, entry_cost_ratio: float, exit_cost_ratio: float)`
- L78 `risk_sized_weight(selected_count: int, loss_distance: float, event_risk_budget: float=0.05)`
- L95 `_natr_failure(code: str, confirmation_date: int, status: str, reason: str, valid_count: int)`
- L116 `compute_confirmation_natr20(panel: pd.DataFrame, code: str, confirmation_date: int, calendar: Iterable[int], observations: int=20)`
- L222 `build_event_natr_ledgers(sector: str, event_id: str, signal_date: int, confirmations: pd.DataFrame, panel: pd.DataFrame, calendar: Iterable[int], observations: int=20, confirmation_status_column: str='repair_status')`
- L279 `_revision(row: dict, rule_id: str, logical_key: str)`
- L286 `reidentify_frame(frame: pd.DataFrame, rule_id: str)`
- L303 `_cash_component_row(sector: str, event_id: str, signal_date: int, code: str, rule_id: str, status: str, equal_weight: float, confirmation: dict, data_failure: bool=False)`
- L352 `_aggregate_daily(sector: str, event_id: str, signal_date: int, rule_id: str, components: pd.DataFrame, component_daily: pd.DataFrame, confirmations: pd.DataFrame, calendar: np.ndarray, capital: float)`
- L432 `simulate_adaptive_event(sector: str, event_id: str, signal_date: int, selection: pd.DataFrame, confirmations: pd.DataFrame, natr_summary: pd.DataFrame, panel: pd.DataFrame, calendar: Iterable[int], component_policy: ComponentPolicy, adaptive_policy: AdaptiveStopPolicy, rule_id: str, k: float, risk_sized: bool, cap20_shadow: bool=False, next_event_boundary_date: int | None=None, sizing_component_policy: ComponentPolicy | None=None, confirmation_status_column: str='repair_status', e2_confirmations: pd.DataFrame | None=None)`

## sector_panic/component_repair_confirmation.py

[打开文件](../../sector_panic/component_repair_confirmation.py)

- L29 `class RepairConfirmationPolicy`
- L39 `RepairConfirmationPolicy.validate(self)`
- L56 `_replace_rule(frame: pd.DataFrame, new_rule: str)`
- L71 `_e2_revision(row: dict, logical_key: str)`
- L78 `_signal_avwap_seed(lookup: pd.DataFrame, code: str, signal_date: int)`
- L89 `build_component_repair_states(sector: str, event_id: str, selection: pd.DataFrame, panel: pd.DataFrame, calendar: Iterable[int], signal_date: int, policy: RepairConfirmationPolicy, next_event_boundary_date: int | None=None, normalized_event_capital: float=1.0)`
- L388 `_aggregate_daily_book(sector: str, event_id: str, signal_date: int, selected_codes: list[str], components: pd.DataFrame, component_daily: pd.DataFrame, confirmations: pd.DataFrame, calendar: np.ndarray, capital: float)`
- L460 `simulate_repair_confirmed_event(sector: str, event_id: str, signal_date: int, selection: pd.DataFrame, panel: pd.DataFrame, calendar: Iterable[int], component_policy: ComponentPolicy, repair_policy: RepairConfirmationPolicy, next_event_boundary_date: int | None=None)`

## sector_panic/component_repair_quality.py

[打开文件](../../sector_panic/component_repair_quality.py)

- L40 `class RepairQualityPolicy`
- L51 `RepairQualityPolicy.validate(self)`
- L70 `_state_row(*, sector: str, event_id: str, signal_date: int, code: str, date: int, offset: int, state: str, reason: str, row, running_low: float, sessions_since_new_low: int, avwap: float, trough_date, higher_low_date, higher_low_low: float, higher_low_confirmed_date, resistance: float, repair_level: float, break_date, hold_count: int, q1_valid: bool, q1_sequence: int, current_q1_confirmed_date, data_failure: bool)`
- L127 `_scan_component(sector: str, event_id: str, signal_date: int, item: dict, lookup: pd.DataFrame, dates: np.ndarray, signal_pos: int, scan_end_pos: int, policy: RepairQualityPolicy, target_budget: float, runtime_censored: bool)`
- L478 `build_repair_quality_states(sector: str, event_id: str, selection: pd.DataFrame, panel: pd.DataFrame, calendar: Iterable[int], signal_date: int, policy: RepairQualityPolicy | None=None, next_event_boundary_date: int | None=None, normalized_event_capital: float=1.0)`

## sector_panic/component_repair_quality_audit.py

[打开文件](../../sector_panic/component_repair_quality_audit.py)

- L34 `_date_position(positions: dict[int, int], value)`
- L39 `_benchmark_return(benchmark: pd.DataFrame | None, code: str, start_date: int, end_date: int)`
- L65 `build_preentry_feature_ledger(original_confirmations: pd.DataFrame, original_states: pd.DataFrame, s2_components: pd.DataFrame, quality_breadth: pd.DataFrame, panels: dict[str, pd.DataFrame], calendar: Iterable[int], benchmark_daily: pd.DataFrame | None=None, sector_benchmark_codes: dict[str, str] | None=None, market_benchmark_code: str='000300.SH')`
- L228 `build_postpath_outcome_ledger(original_confirmations: pd.DataFrame, s2_components: pd.DataFrame, panels: dict[str, pd.DataFrame], calendar: Iterable[int])`
- L331 `build_funnel_ledger(selection: pd.DataFrame, original_confirmations: pd.DataFrame, q1_confirmations: pd.DataFrame, q2_eligibility: pd.DataFrame, arm_components: pd.DataFrame | None=None)`
- L397 `_auc(values: pd.Series, labels: pd.Series)`
- L408 `_bh_qvalues(pvalues: list[float])`
- L427 `build_feature_episode_statistics(features: pd.DataFrame, outcomes: pd.DataFrame, event_context: pd.DataFrame, *, seed: int=20260817, bootstrap_runs: int=10000)`

## sector_panic/config.py

[打开文件](../../sector_panic/config.py)

- L46 `class SectorConfig`
- L62 `SectorConfig.round_trip_bps(self)`
- L66 `_as_number(value: Any, label: str, errors: list[str], cast=float)`
- L95 `_valid_date8(s: str)`
- L109 `validate_config(raw: dict, config_path: str='<unknown>')`
- L531 `load_config(path: str | Path)`

## sector_panic/continuation_value_exit.py

[打开文件](../../sector_panic/continuation_value_exit.py)

- L38 `class ContinuationPolicy`
- L51 `_close_map(frame: pd.DataFrame, column: str='close')`
- L65 `_boundary_position(entry_position: int, calendar: np.ndarray, maximum_holding_sessions: int, next_event_entry_date: int | None)`
- L82 `_first_sell_fill(lookup: pd.DataFrame, code: str, calendar: np.ndarray, start_position: int)`
- L102 `_net_exit_value(close: float, entry_price: float, entry_cost_ratio: float, exit_cost_ratio: float)`
- L118 `_continuation_label(lookup: pd.DataFrame, code: str, entry_price: float, current_position: int, boundary_position: int, calendar: np.ndarray, entry_cost_ratio: float, exit_cost_ratio: float)`
- L160 `_feature_row(lookup: pd.DataFrame, code: str, signal_position: int, entry_position: int, current_position: int, calendar: np.ndarray, entry_price: float, signal_natr: float, sector_close: dict[int, float], benchmark_close: dict[int, float], policy: ContinuationPolicy)`
- L262 `build_component_decision_rows(sector: str, event_id: str, episode_id: str, signal_date: int, entry_date: int, code: str, item: dict, lookup: pd.DataFrame, calendar: Iterable[int], sector_index: pd.DataFrame, benchmark_index: pd.DataFrame, policy: ContinuationPolicy, next_event_entry_date: int | None=None)`
- L332 `_fit_ridge(x: np.ndarray, y: np.ndarray, alpha: float)`
- L346 `_predict(model: dict, x: np.ndarray)`
- L351 `_inner_alpha(train: pd.DataFrame, alpha_grid: tuple[float, ...])`
- L373 `fit_loeo_predictions(rows: pd.DataFrame, alpha_grid: Iterable[float]=(0.1, 1.0, 10.0, 100.0))`
- L428 `fit_time_order_predictions(rows: pd.DataFrame, cutoff: int=20240101, alpha_grid: Iterable[float]=(0.1, 1.0, 10.0, 100.0))`
- L476 `simulate_r7_component_event(sector: str, event_id: str, signal_date: int, entry_date: int, selection: pd.DataFrame, panel: pd.DataFrame, calendar: Iterable[int], predictions: pd.DataFrame, policy: ContinuationPolicy, next_event_entry_date: int | None=None)`

## sector_panic/cost.py

[打开文件](../../sector_panic/cost.py)

- L30 `class RoundTripCost`
- L46 `RoundTripCost.__post_init__(self)`
- L68 `RoundTripCost.ratio(self)`
- L73 `RoundTripCost.entry_ratio(self)`
- L78 `RoundTripCost.exit_ratio(self)`
- L82 `RoundTripCost.half_ratio(self)`
- L86 `RoundTripCost.weighted_ratio(self, weight: float)`
- L90 `RoundTripCost.to_dict(self)`
- L94 `RoundTripCost.from_bps(cls, round_trip_bps: int, entry_bps: int | None=None, exit_bps: int | None=None)`
- L127 `convert_legacy_cost(cost_bps: int | float, script: str)`
- L185 `_run_acceptance_tests()`

## sector_panic/entry_exit_attribution.py

[打开文件](../../sector_panic/entry_exit_attribution.py)

- L70 `class AttributionIntegrityError`
- L74 `b0_entry_kwargs()`
- L93 `_reject_flag_overrides(overrides: Mapping[str, object])`
- L106 `_simulate_b0(*, confirmation_invalidation: bool, default_rule_id: str, sector: str, event_id: str, signal_date: int, selected_count: int, item: dict, panel: pd.DataFrame, calendar: Iterable[int], next_event_boundary_date: int | None, policy: V8Policy, rule_id: str | None=None, **overrides: object)`
- L140 `simulate_b0_v11_component(*, sector: str, event_id: str, signal_date: int, selected_count: int, item: dict, panel: pd.DataFrame, calendar: Iterable[int], next_event_boundary_date: int | None, policy: V8Policy, rule_id: str=B0_V11_RULE_ID, **overrides: object)`
- L173 `_bool(value: object)`
- L200 `_copy_frame(frame: pd.DataFrame | None)`
- L204 `_with_matrix_revision(frame: pd.DataFrame, rule_id: str)`
- L214 `_first_v12_candidate(daily: pd.DataFrame, *, lookup: pd.DataFrame, code: str, calendar: np.ndarray, entry_price: float, confirmation_close: float, repair_level: float, boundary_pos: int)`
- L308 `_attempt_sequence_max(attempts: pd.DataFrame)`
- L315 `_overlay_attempt(*, base: dict, rule_id: str, decision_date: int, target_date: int, sequence: int, status: str, blocker: str | None, quantity: float, price: float, fee_ratio: float, cash_after: float)`
- L363 `_mark_overlay_daily(row: dict, *, rule_id: str, cash: float, quantity: float, close: float, fee_total: float, flat: bool, data_failure: bool, trigger_date: int, due_date: int)`
- L399 `_mark_v12_data_failure(frames: dict[str, pd.DataFrame], *, rule_id: str)`
- L422 `_apply_v12_overlay(base: dict[str, pd.DataFrame], *, sector: str, event_id: str, signal_date: int, rule_id: str, item: dict, panel: pd.DataFrame, calendar: Iterable[int], next_event_boundary_date: int | None, policy: V8Policy)`
- L714 `simulate_b0_v12_component(*, sector: str, event_id: str, signal_date: int, selected_count: int, item: dict, panel: pd.DataFrame, calendar: Iterable[int], next_event_boundary_date: int | None, policy: V8Policy, rule_id: str=B0_V12_RULE_ID, **overrides: object)`
- L759 `_key_columns(left: pd.DataFrame, right: pd.DataFrame)`
- L764 `_normal_bool(value: object)`
- L768 `_same_value(left: object, right: object, *, numeric: bool=False)`
- L789 `assert_fill_freeze(overlay_component: pd.DataFrame, frozen_b0_component: pd.DataFrame)`
- L895 `_frozen_b0_winners(frozen_b0_component: pd.DataFrame, *, rule_id: str=B0_V8_RULE_ID)`
- L919 `_bool_series(series: pd.Series)`
- L923 `_date_number(value: object)`
- L927 `b0_winner_retention(frozen_b0_component: pd.DataFrame, overlay_component: pd.DataFrame, *, denominator_count: int=WINNER_DENOMINATOR, kill_if_numerator_ge: int=WINNER_CHOP_THRESHOLD, rule_id: str=B0_V8_RULE_ID)`
- L1051 `canonical_frame(frame: pd.DataFrame, sort_keys: Iterable[str] | None=None)`
- L1061 `canonical_frame_bytes(frame: pd.DataFrame, sort_keys: Iterable[str] | None=None)`
- L1071 `assert_dual_runtime_identical(runtime_a: Mapping[str, pd.DataFrame], runtime_b: Mapping[str, pd.DataFrame], *, sort_keys: Mapping[str, Iterable[str]] | None=None)`
- L1095 `_event_metric_frame(events: pd.DataFrame)`
- L1109 `event_statistics(events: pd.DataFrame)`
- L1146 `paired_event_statistics(candidate_events: pd.DataFrame, control_events: pd.DataFrame, *, bootstrap_seed: int=20260906, bootstrap_runs: int=10000)`
- L1255 `b0_event_results(components: pd.DataFrame)`
- L1261 `overlay_source_hash(path: str | Path)`

## sector_panic/extension_no_chase_v10.py

[打开文件](../../sector_panic/extension_no_chase_v10.py)

- L62 `class V8Policy`
- L77 `V8Policy.validate(self)`
- L103 `V8Policy.doubled_cost(self)`
- L111 `_revision(row: dict, logical_key: str)`
- L121 `_bool(value: object)`
- L127 `_int_or_none(value: object)`
- L132 `_required_number(item: dict, name: str)`
- L139 `class _AnchorBook`
- L142 `_AnchorBook.__init__(self, lookup: pd.DataFrame, calendar: np.ndarray, code: str, signal_date: int, repair_level: float, natr20: float, policy: V8Policy)`
- L164 `_AnchorBook.snapshot(self, trade_date: int)`
- L234 `_cash_component(*, sector: str, event_id: str, signal_date: int, rule_id: str, code: str, target_budget: float, terminal_reason: str, observation_date: int, data_failure: bool=False, natr20: float=np.nan, stop_distance: float=np.nan)`
- L283 `_anchor_ledger_row(*, sector: str, event_id: str, signal_date: int, rule_id: str, code: str, snapshot: dict, higher_low_low: float, panic_low: float, phase: str, dual_buffer_natr: float=0.0)`
- L334 `_failure_type(anchor: dict)`
- L344 `simulate_v8_component(*, sector: str, event_id: str, signal_date: int, rule_id: str, selected_count: int, item: dict, panel: pd.DataFrame, calendar: Iterable[int], next_event_boundary_date: int | None, entry_mode: str, structural_exit: bool, policy: V8Policy, entry_review_sessions: int | None=None, entry_review_mode: str | None=None, dual_buffer_natr: float | None=None, dual_two_close_confirmation: bool | None=None, confirmation_close_floor: bool=False, confirmation_invalidation: bool=False)`
- L1009 `aggregate_event_results(components: pd.DataFrame)`
- L1052 `build_stop_execution_decomposition(components: pd.DataFrame, daily: pd.DataFrame, attempts: pd.DataFrame)`
- L1112 `build_mfe_giveback_conditional(components: pd.DataFrame, daily: pd.DataFrame)`
- L1148 `nearest_rank_q10(values: Iterable[float])`
- L1156 `episode_bootstrap_mean_ci(episode_values: pd.Series, *, seed: int=20260821, runs: int=10000)`
- L1174 `lower_tail_cvar(values: Iterable[float], proportion: float=0.1)`

## sector_panic/extension_no_chase_v12.py

[打开文件](../../sector_panic/extension_no_chase_v12.py)

- L29 `_bool(value: object)`
- L35 `_concat_with_columns(frames: list[pd.DataFrame])`
- L40 `_add_attempt(*, base: dict, rule_id: str, decision_date: int, target_date: int, sequence: int, status: str, blocker: str | None, quantity: float, price: float, fee_ratio: float, cash_after: float)`
- L87 `_mark_daily_row(row: dict, *, rule_id: str, cash: float, quantity: float, close: float, fee_total: float, exit_submitted: bool, exit_reason: str, flat: bool, data_failure: bool)`
- L117 `_first_v12_candidate(daily: pd.DataFrame, *, lookup: pd.DataFrame, code: str, calendar: np.ndarray, entry_price: float, confirmation_close: float, repair_level: float, boundary_pos: int)`
- L189 `simulate_v12_component(*, sector: str, event_id: str, signal_date: int, rule_id: str, selected_count: int, item: dict, panel: pd.DataFrame, calendar: Iterable[int], next_event_boundary_date: int | None, policy)`

## sector_panic/extension_no_chase_v12_r1.py

[打开文件](../../sector_panic/extension_no_chase_v12_r1.py)

- L44 `_bool(value: object)`
- L50 `_json(value: object)`
- L56 `_int_or_none(value: object)`
- L61 `_revision(row: dict, logical_key: str)`
- L71 `_ordered_signals(signals: Iterable[str])`
- L78 `_normalise_base_frames(frames: dict[str, pd.DataFrame], rule_id: str)`
- L126 `_inventory_from_base(component: pd.DataFrame, daily: pd.DataFrame, attempts: pd.DataFrame)`
- L157 `_candidate_step(*, session: int, suspended: bool, close: float, confirmation_close: float, repair_level: float, stop_signal: bool, position: int, boundary_pos: int, in_watch: bool, below_count: int)`
- L206 `_make_attempt(*, base: dict, rule_id: str, sequence: int, retry_sequence: int, decision_date: int, target_date: int, status: str, blocker: str | None, quantity: float, price: float, fee_ratio: float, cash_before: float, order_owner: str, base_order_id: str, decision_reason: str, market_row)`
- L234 `_control_result(base: dict[str, pd.DataFrame], rule_id: str)`
- L244 `simulate_v12_r1_component(*, sector: str, event_id: str, signal_date: int, rule_id: str, selected_count: int, item: dict, panel: pd.DataFrame, calendar: Iterable[int], next_event_boundary_date: int | None, policy, enable_v12: bool=True)`

## sector_panic/extension_no_chase_v14.py

[打开文件](../../sector_panic/extension_no_chase_v14.py)

- L76 `class V8Policy`
- L91 `V8Policy.validate(self)`
- L117 `V8Policy.doubled_cost(self)`
- L125 `_revision(row: dict, logical_key: str)`
- L135 `_bool(value: object)`
- L141 `_int_or_none(value: object)`
- L146 `_required_number(item: dict, name: str)`
- L153 `class _AnchorBook`
- L156 `_AnchorBook.__init__(self, lookup: pd.DataFrame, calendar: np.ndarray, code: str, signal_date: int, repair_level: float, natr20: float, policy: V8Policy)`
- L178 `_AnchorBook.snapshot(self, trade_date: int)`
- L248 `_cash_component(*, sector: str, event_id: str, signal_date: int, rule_id: str, code: str, target_budget: float, terminal_reason: str, observation_date: int, data_failure: bool=False, natr20: float=np.nan, stop_distance: float=np.nan)`
- L298 `_anchor_ledger_row(*, sector: str, event_id: str, signal_date: int, rule_id: str, code: str, snapshot: dict, higher_low_low: float, panic_low: float, phase: str, dual_buffer_natr: float=0.0)`
- L349 `_failure_type(anchor: dict)`
- L359 `simulate_v8_component(*, sector: str, event_id: str, signal_date: int, rule_id: str, selected_count: int, item: dict, panel: pd.DataFrame, calendar: Iterable[int], next_event_boundary_date: int | None, entry_mode: str, structural_exit: bool, policy: V8Policy, entry_review_sessions: int | None=None, entry_review_mode: str | None=None, dual_buffer_natr: float | None=None, dual_two_close_confirmation: bool | None=None, confirmation_close_floor: bool=False, confirmation_invalidation: bool=False, confirmation_floor_epsilon: bool=False)`
- L1048 `aggregate_event_results(components: pd.DataFrame)`
- L1091 `build_stop_execution_decomposition(components: pd.DataFrame, daily: pd.DataFrame, attempts: pd.DataFrame)`
- L1151 `build_mfe_giveback_conditional(components: pd.DataFrame, daily: pd.DataFrame)`
- L1187 `nearest_rank_q10(values: Iterable[float])`
- L1195 `episode_bootstrap_mean_ci(episode_values: pd.Series, *, seed: int=20260821, runs: int=10000)`
- L1213 `lower_tail_cvar(values: Iterable[float], proportion: float=0.1)`

## sector_panic/extension_no_chase_v8.py

[打开文件](../../sector_panic/extension_no_chase_v8.py)

- L42 `class V8Policy`
- L53 `V8Policy.validate(self)`
- L67 `V8Policy.doubled_cost(self)`
- L75 `_revision(row: dict, logical_key: str)`
- L85 `_bool(value: object)`
- L91 `_int_or_none(value: object)`
- L96 `_required_number(item: dict, name: str)`
- L103 `class _AnchorBook`
- L106 `_AnchorBook.__init__(self, lookup: pd.DataFrame, calendar: np.ndarray, code: str, signal_date: int, repair_level: float, natr20: float, policy: V8Policy)`
- L128 `_AnchorBook.snapshot(self, trade_date: int)`
- L197 `_cash_component(*, sector: str, event_id: str, signal_date: int, rule_id: str, code: str, target_budget: float, terminal_reason: str, observation_date: int, data_failure: bool=False, natr20: float=np.nan, stop_distance: float=np.nan)`
- L245 `_anchor_ledger_row(*, sector: str, event_id: str, signal_date: int, rule_id: str, code: str, snapshot: dict, higher_low_low: float, panic_low: float, phase: str)`
- L288 `_failure_type(anchor: dict)`
- L298 `simulate_v8_component(*, sector: str, event_id: str, signal_date: int, rule_id: str, selected_count: int, item: dict, panel: pd.DataFrame, calendar: Iterable[int], next_event_boundary_date: int | None, entry_mode: str, structural_exit: bool, policy: V8Policy)`
- L767 `aggregate_event_results(components: pd.DataFrame)`
- L810 `build_stop_execution_decomposition(components: pd.DataFrame, daily: pd.DataFrame, attempts: pd.DataFrame)`
- L870 `build_mfe_giveback_conditional(components: pd.DataFrame, daily: pd.DataFrame)`
- L906 `nearest_rank_q10(values: Iterable[float])`
- L914 `episode_bootstrap_mean_ci(episode_values: pd.Series, *, seed: int=20260821, runs: int=10000)`
- L932 `lower_tail_cvar(values: Iterable[float], proportion: float=0.1)`

## sector_panic/extension_no_chase_v9.py

[打开文件](../../sector_panic/extension_no_chase_v9.py)

- L48 `class V8Policy`
- L63 `V8Policy.validate(self)`
- L89 `V8Policy.doubled_cost(self)`
- L97 `_revision(row: dict, logical_key: str)`
- L107 `_bool(value: object)`
- L113 `_int_or_none(value: object)`
- L118 `_required_number(item: dict, name: str)`
- L125 `class _AnchorBook`
- L128 `_AnchorBook.__init__(self, lookup: pd.DataFrame, calendar: np.ndarray, code: str, signal_date: int, repair_level: float, natr20: float, policy: V8Policy)`
- L150 `_AnchorBook.snapshot(self, trade_date: int)`
- L220 `_cash_component(*, sector: str, event_id: str, signal_date: int, rule_id: str, code: str, target_budget: float, terminal_reason: str, observation_date: int, data_failure: bool=False, natr20: float=np.nan, stop_distance: float=np.nan)`
- L268 `_anchor_ledger_row(*, sector: str, event_id: str, signal_date: int, rule_id: str, code: str, snapshot: dict, higher_low_low: float, panic_low: float, phase: str, dual_buffer_natr: float=0.0)`
- L319 `_failure_type(anchor: dict)`
- L329 `simulate_v8_component(*, sector: str, event_id: str, signal_date: int, rule_id: str, selected_count: int, item: dict, panel: pd.DataFrame, calendar: Iterable[int], next_event_boundary_date: int | None, entry_mode: str, structural_exit: bool, policy: V8Policy, entry_review_sessions: int | None=None, entry_review_mode: str | None=None, dual_buffer_natr: float | None=None, dual_two_close_confirmation: bool | None=None)`
- L887 `aggregate_event_results(components: pd.DataFrame)`
- L930 `build_stop_execution_decomposition(components: pd.DataFrame, daily: pd.DataFrame, attempts: pd.DataFrame)`
- L990 `build_mfe_giveback_conditional(components: pd.DataFrame, daily: pd.DataFrame)`
- L1026 `nearest_rank_q10(values: Iterable[float])`
- L1034 `episode_bootstrap_mean_ci(episode_values: pd.Series, *, seed: int=20260821, runs: int=10000)`
- L1052 `lower_tail_cvar(values: Iterable[float], proportion: float=0.1)`

## sector_panic/hold_sensitivity.py

[打开文件](../../sector_panic/hold_sensitivity.py)

- L35 `_position_map(calendar: np.ndarray)`
- L39 `cell_metrics(ledger_cell: pd.DataFrame, calendar: np.ndarray)`
- L120 `hold_day_distribution(realized: pd.DataFrame, calendar: np.ndarray)`
- L148 `bootstrap_stat(diffs: np.ndarray, seed: int, n_boot: int=5000, block_size: int | None=None, stat=np.mean)`
- L181 `bootstrap_cluster_stat(values: np.ndarray, groups: np.ndarray, seed: int, n_boot: int=5000, block_size: int | None=None, stat=np.mean)`
- L238 `_realized_frame(frame: pd.DataFrame)`
- L247 `_status_breakdown(frame: pd.DataFrame)`
- L256 `_status_breakdown_for_keys(frame: pd.DataFrame, keys: set[tuple], key_column: str='_pair_key')`
- L270 `_status_pairs(base: pd.DataFrame, arm: pd.DataFrame, keys: set[tuple], key_column: str='_pair_key')`
- L290 `paired_diff_stats(base: pd.DataFrame, arm: pd.DataFrame, seed: int, n_boot: int=5000, block_sizes: tuple[int, ...]=(2, 3))`
- L403 `equal_weight_aggregate(rows: list[dict])`
- L420 `direction_check(per_split_mean_diffs: dict[str, float | None])`
- L445 `raw_path_curve(event_paths: list[np.ndarray], boundary_days: list[int | None], max_day: int=MAX_CURVE_DAY)`
- L486 `strategy_net_curves(event_paths: list[np.ndarray], exit_positions: list[int | None], exit_returns: list[float | None], weights: list[float | None] | None=None, add_positions: list[int | None] | None=None, round_trip_costs: list[float] | None=None, max_day: int=MAX_CURVE_DAY)`
- L582 `stop_day_counts(ledger_cell: pd.DataFrame, calendar: np.ndarray, max_day: int=MAX_CURVE_DAY)`

## sector_panic/integrity.py

[打开文件](../../sector_panic/integrity.py)

- L28 `class VerifiedRuntimeSnapshot`
- L35 `sha256_file(path: Path)`
- L43 `csv_row_count(path: Path)`
- L52 `_safe_snapshot_path(root: Path, relative: str)`
- L63 `verify_runtime_snapshot(runtime_dir: str | Path, required_tables: tuple[str, ...]=RUNTIME_TABLES, validate_rows: bool=True)`
- L133 `_present(value: object)`
- L137 `current_rows(frame: pd.DataFrame)`
- L157 `supersede_chain_integrity(frame: pd.DataFrame, ledger_name: str)`
- L244 `supersede_chain_integrity_for_ledgers(named_frames: dict[str, pd.DataFrame])`
- L266 `_layer_key(record: dict)`
- L278 `_same_value(left: object, right: object)`
- L290 `cross_file_layer_consistency(e2_confirmations: pd.DataFrame, q1_confirmations: pd.DataFrame, q2_eligibility: pd.DataFrame, funnel: pd.DataFrame, components: pd.DataFrame)`

## sector_panic/phase0b_data_audit.py

[打开文件](../../sector_panic/phase0b_data_audit.py)

- L24 `class AuditPolicy`
- L33 `expected_months(start: int, end: int)`
- L38 `_normalize_weights(weights: pd.DataFrame)`
- L53 `audit_monthly_membership(weights: pd.DataFrame, sector_specs: dict, sectors: list[str], start: int, end: int, policy: AuditPolicy)`
- L123 `build_monthly_membership_changes(membership_audit: pd.DataFrame, snapshots: dict[str, dict[int, pd.DataFrame]], sectors: list[str], months: list[int])`
- L164 `build_monthly_overlap_matrix(snapshots: dict[str, dict[int, pd.DataFrame]], pairs: list[list[str]], months: list[int], require_synchronous_dates: bool=True)`
- L221 `_normalize_table_dates(frame: pd.DataFrame, date_column: str='trade_date')`
- L230 `audit_tradability(weights: pd.DataFrame, prices: pd.DataFrame, limits: pd.DataFrame, suspends: pd.DataFrame, stock_status: pd.DataFrame, namechange: pd.DataFrame, calendar: Iterable[int], sector_specs: dict, sectors: list[str], start: int, end: int, policy: AuditPolicy)`
- L364 `audit_pretrade_diversification(weights: pd.DataFrame, prices: pd.DataFrame, limits: pd.DataFrame, suspends: pd.DataFrame, stock_status: pd.DataFrame, namechange: pd.DataFrame, index_daily: pd.DataFrame, calendar: Iterable[int], sector_specs: dict, sectors: list[str], signal_config: dict, basket_config: dict, start: int, end: int, amount_multiplier: float, policy: AuditPolicy)`
- L485 `audit_lithium_template(template: dict, required_fields: list[str])`

## sector_panic/phase1_execution.py

[打开文件](../../sector_panic/phase1_execution.py)

- L25 `class Phase1Policy`
- L39 `Phase1Policy.__post_init__(self)`
- L58 `class EventExecution`
- L65 `normalize_calendar(values: Iterable[int])`
- L72 `_lookup(panel: pd.DataFrame)`
- L101 `build_execution_lookup(panel: pd.DataFrame)`
- L106 `_row(lookup: pd.DataFrame, code: str, trade_date: int)`
- L116 `_finite(value)`
- L124 `_with_revision(row: dict, logical_key: str)`
- L134 `select_event_basket(sector: str, event_id: str, signal_date: int, universe: pd.DataFrame, panel: pd.DataFrame, calendar: Iterable[int], policy: Phase1Policy)`
- L235 `_attempt_status(row, side: str)`
- L254 `_decision_ratio(positions: dict[str, dict], lookup: pd.DataFrame, trade_date: int)`
- L277 `_mark_open_positions(positions: dict[str, dict], lookup: pd.DataFrame, trade_date: int)`
- L304 `simulate_event_rule(sector: str, event_id: str, signal_date: int, entry_date: int, selection: pd.DataFrame, panel: pd.DataFrame, calendar: Iterable[int], rule_id: str, policy: Phase1Policy, next_event_entry_date: int | None=None)`
- L659 `execute_paired_event(sector: str, event_id: str, signal_date: int, entry_date: int, selection: pd.DataFrame, panel: pd.DataFrame, calendar: Iterable[int], policy: Phase1Policy, next_event_entry_date: int | None=None)`
- L686 `validate_execution_closure(event_ledger: pd.DataFrame, attempt_ledger: pd.DataFrame, inventory_ledger: pd.DataFrame, daily_ledger: pd.DataFrame, calendar: Iterable[int], normalized_event_capital: float=1.0, tolerance: float=1e-10)`
- L797 `build_revision_ledger(named_frames: dict[str, pd.DataFrame])`

## sector_panic/rebuild/__init__.py

[打开文件](../../sector_panic/rebuild/__init__.py)

无顶层函数/类；阅读模块常量、导入或入口逻辑。

## sector_panic/rebuild/account.py

[打开文件](../../sector_panic/rebuild/account.py)

- L14 `_d(value)`
- L18 `round_cash(value, places: Decimal=TWOPLACES)`
- L23 `class ResearchBook`
- L30 `ResearchBook.nav(self)`
- L33 `ResearchBook.mark_nav(self, raw_mark: float)`
- L37 `apply_research_buy(book: ResearchBook, quantity: float, price: float, fee_ratio: float)`
- L55 `apply_research_sell(book: ResearchBook, quantity: float, price: float, fee_ratio: float)`
- L71 `reserve_working_buy(book: ResearchBook, budget: float)`
- L80 `release_reserve(book: ResearchBook, budget: float, confirmed: bool)`
- L91 `nav_identity(cash: float, shares: float, mark: float, frozen_cash: float)`
- L98 `class ShadowBook`
- L107 `ShadowBook.nav(self, mark: Decimal)`
- L111 `round_lot(shares: float, lot_size: int)`
- L117 `apply_corporate_action(book: ShadowBook, *, split_ratio: Optional[float]=None, cash_dividend: Optional[Decimal]=None)`
- L137 `risk_caps_ok(*, order_budget: float, working_buy_budget: float, nav: float, sector_exposure: float, name_exposure: float, policy: RebuildPolicy, ignore_working: bool=False, strategy_exposure: float=0.0, working_sector_budget: float=0.0, working_name_budget: float=0.0)`
- L167 `research_return(assigned: float, final_nav: float)`
- L173 `invested_return(deployed: float, pnl: float)`
- L179 `scale_invariant(budget_a: float, pnl_a: float, budget_b: float, pnl_b: float)`

## sector_panic/rebuild/aggregation.py

[打开文件](../../sector_panic/rebuild/aggregation.py)

- L28 `map_upstream_status(repair_status: str)`
- L41 `cash_complete_zero(*, observation_complete: bool, determined_no_entry: bool)`
- L59 `counts(results: pd.DataFrame)`
- L70 `integrity_violations(results: pd.DataFrame, frozen_keys: Iterable[tuple], key_cols: tuple[str, ...]=('sector', 'event_id', 'signal_date'))`
- L119 `economic_gate_status(issues: list[str])`
- L125 `evaluate_gates(results: pd.DataFrame, frozen_keys: Iterable[tuple], *, dropna: bool=False, skip_integrity: bool=False, artificial_pass: bool=False, economic_contract: Optional[dict]=None, control: Optional[pd.DataFrame]=None)`
- L188 `pair_on_frozen_keys(candidate: pd.DataFrame, control: pd.DataFrame, frozen_keys: Iterable[tuple], key_cols: tuple[str, ...]=('sector', 'event_id', 'signal_date'))`

## sector_panic/rebuild/contracts.py

[打开文件](../../sector_panic/rebuild/contracts.py)

- L25 `class ResultStatus`
- L36 `class OrderStatus`
- L46 `class MatchMode`
- L53 `class RebuildPolicy`
- L70 `RebuildPolicy.extension_width(self, natr20: float)`
- L75 `class FrozenOrder`
- L95 `FrozenOrder.__post_init__(self)`
- L99 `FrozenOrder.frozen_fields(self)`
- L112 `class FillRecord`
- L124 `class EventResult`
- L143 `EventResult.to_dict(self)`
- L147 `load_scope(path: Path | None=None)`
- L153 `sha256_file(path: Path)`
- L158 `legacy_source_status(scope: dict | None=None)`
- L171 `assert_legacy_hashes_unchanged(scope: dict | None=None)`
- L186 `validate_run_id(run_id: str)`
- L194 `resolve_run_dir(run_id: str, *, kind: str='diagnostic')`
- L215 `assert_fresh_run_dir(out_root: Path)`
- L233 `cannot_refresh_frozen_hash(scope: dict, new_hash: str)`

## sector_panic/rebuild/coverage_evidence.py

[打开文件](../../sector_panic/rebuild/coverage_evidence.py)

- L7 `_key(row: dict)`
- L15 `_comp(row: dict)`
- L19 `_synthetic(test_evidence: dict | None, nodeids: list[str], *, current_source_hash: str | None=None)`
- L47 `_attempts_for(attempts: list[dict], key: tuple, side: str | None=None)`
- L63 `build_coverage_evidence(*, results: list[dict], fills: list[dict], orders: list[dict], attempts: list[dict], risk: list[dict], test_evidence: dict | None=None, current_source_hash: str | None=None)`

## sector_panic/rebuild/data_guard.py

[打开文件](../../sector_panic/rebuild/data_guard.py)

- L14 `class GuardFailure`
- L19 `reject_mixed_price_fields(row: dict)`
- L31 `reject_duplicate_keys(frame: pd.DataFrame, keys: Iterable[str])`
- L40 `reject_missing_price(row: dict)`
- L50 `snapshot_stale(snapshot_date: int, query_date: int, calendar: list[int], max_sessions: int=PIT_STALE_SESSIONS_DEFAULT)`
- L65 `infinite_last_snapshot_end()`
- L70 `active_universe(snapshots: pd.DataFrame, query_date: int, calendar: list[int], policy: RebuildPolicy | None=None)`
- L95 `field_available(available_at: int, decision_date: int)`
- L99 `filter_asof_fields(rows: list[dict], decision_date: int)`

## sector_panic/rebuild/dependence.py

[打开文件](../../sector_panic/rebuild/dependence.py)

- L11 `session_span(calendar: list[int], start: int, sessions: int)`
- L21 `legal_interval_end(*, d0: int, calendar: list[int], policy: RebuildPolicy, actual_flat: Optional[int]=None, blocked_exit_end: Optional[int]=None, pending: bool=False)`
- L47 `merge_intervals(rows: list[dict])`
- L70 `group_events(events: pd.DataFrame, calendar: list[int], policy: RebuildPolicy)`
- L109 `purge_groups_crossing_split(groups: pd.DataFrame, *, split_date: int, label_end: dict[str, int], parent_flat: dict[str, int], feature_available: dict[str, int])`
- L131 `train_standardize(train_values: Iterable[float], apply_values: Iterable[float])`

## sector_panic/rebuild/diagnostic_inputs.py

[打开文件](../../sector_panic/rebuild/diagnostic_inputs.py)

- L36 `class InputIssue`
- L43 `class DiagnosticBundle`
- L58 `DiagnosticBundle.blocked(self)`
- L65 `load_contract(path: Path | None=None)`
- L71 `resolve_diagnostic_contract(raw: dict)`
- L96 `_check_hash(path: Path, expected: str, issues: list[InputIssue], key=())`
- L105 `verify_input_hashes(contract: dict)`
- L119 `_int_or_none(value)`
- L133 `_float_or_none(value)`
- L145 `_close_enough(left: Optional[float], right: Optional[float], tol: float)`
- L151 `risk_inputs_enabled(contract: dict)`
- L155 `_min_adj_low(bars: dict[int, dict], calendar: list[int], start_exclusive: int, end_inclusive: int)`
- L183 `prove_confirmation_snapshot(rec: dict, *, bars: dict[int, dict], calendar: list[int], as_of: Optional[int])`
- L277 `session_plus(calendar: list[int], date: int, n: int)`
- L287 `observable_status(spec: dict, as_of: Optional[int], calendar: list[int])`
- L310 `cumulative_adj_avwap(code_bars: dict[int, dict], signal_date: int, calendar: list[int], as_of: Optional[int])`
- L346 `_vwap(amount, vol)`
- L356 `load_sample_keys(contract: dict)`
- L368 `sample_role_map(contract: dict)`
- L384 `event_replay_until_map(contract: dict)`
- L389 `adapt_bundle(contract: dict | None=None, *, as_of: Optional[int]=None)`

## sector_panic/rebuild/diagnostic_manifest.py

[打开文件](../../sector_panic/rebuild/diagnostic_manifest.py)

- L15 `environment_record()`
- L24 `build_run_manifest(*, run_id: str, as_of: int | None, contract_path: Path, status: str, extra: dict | None=None)`

## sector_panic/rebuild/diagnostic_runner.py

[打开文件](../../sector_panic/rebuild/diagnostic_runner.py)

- L21 `_offset_date(calendar: list[int], date: int, n: int)`
- L30 `replay_bundle(bundle: DiagnosticBundle, *, as_of: Optional[int]=None)`
- L281 `run_diagnostic(*, run_id: str, out_dir: Path, contract_path: Path | None=None, as_of: Optional[int]=None, test_evidence: dict | None=None)`

## sector_panic/rebuild/entry_policy.py

[打开文件](../../sector_panic/rebuild/entry_policy.py)

- L13 `activity_anchor(repair_level: float, signal_avwap: float)`
- L17 `buy_limit_from_anchor(anchor: float, width: float)`
- L22 `buy_limit_legacy_max_ac(anchor: float, confirmation_close: float, width: float)`
- L28 `class ReviewDecision`
- L37 `review_entry(*, decision_date: int, d0: int, calendar: list[int], decision_close: float, confirmation_close: float, repair_level: float, signal_avwap: float, natr20: float, structure_ok: bool, policy: RebuildPolicy, future_close: Optional[float]=None)`
- L106 `preset_quantity(budget: float, limit: float, entry_cost_ratio: float)`

## sector_panic/rebuild/event_engine.py

[打开文件](../../sector_panic/rebuild/event_engine.py)

- L36 `next_session(calendar: list[int], date: int)`
- L46 `session_plus(calendar: list[int], date: int, n: int)`
- L56 `offset_from(calendar: list[int], d0: int, n: int)`
- L61 `class EngineConfig`
- L85 `class EngineState`
- L109 `EngineState.snapshot(self)`
- L135 `class EventEngine`
- L136 `EventEngine.__init__(self, calendar: list[int], bars: dict[int, dict], policy: RebuildPolicy, config: EngineConfig, signal_avwap: dict[int, float] | None=None, structure_ok: dict[int, bool] | None=None, event_arrivals: dict[int, int] | None=None, structure_detail: dict[int, dict] | None=None)`
- L165 `EventEngine.restore(self, snap: dict)`
- L190 `EventEngine._stop_mode(self)`
- L202 `EventEngine._structure_flag(self, date: int)`
- L214 `EventEngine._bar(self, date: int)`
- L217 `EventEngine._avwap(self, date: int)`
- L225 `EventEngine._finite_close(self, bar: dict | None)`
- L237 `EventEngine._in_wait_window(self, date: int)`
- L244 `EventEngine._observation_gap(self, date: int)`
- L254 `EventEngine.run_until(self, asof: int)`
- L277 `EventEngine._step(self, date: int, asof: int)`
- L324 `EventEngine._match_working(self, date: int)`
- L438 `EventEngine._maybe_submit_buy(self, date: int, asof: int)`
- L540 `EventEngine._append_risk(self, date: int, **fields)`
- L572 `EventEngine._compute_stop_hit(self, px: Optional[float])`
- L592 `EventEngine._manage_exit(self, date: int, asof: int)`
- L682 `EventEngine._submit_sell(self, submit_date: int, target_date: int, reason: str)`
- L699 `EventEngine._window_observed(self, asof: int)`
- L711 `EventEngine._finalize_asof(self, asof: int)`
- L747 `EventEngine.result(self)`
- L779 `EventEngine._last_mark(self, asof: Optional[int]=None)`

## sector_panic/rebuild/execution.py

[打开文件](../../sector_panic/rebuild/execution.py)

- L13 `class MatchResult`
- L23 `match_daily_close_proxy(order: FrozenOrder, bar: dict, *, cost_ratio: float, confirmation_close: Optional[float]=None, reject_below_confirmation: bool=False)`
- L85 `close_auction_rule(year: int, exchange: str)`
- L95 `shadow_execution_status(*, has_auction_capacity: bool, has_receipt: bool)`
- L105 `apply_receipt(inventory: dict[str, float], cash: float, fill_id: str, seen_receipts: set[str], shares: float, notional: float, fee: float, side: str, allow_duplicate: bool=False, ts_code: str='')`

## sector_panic/rebuild/fill_sample.py

[打开文件](../../sector_panic/rebuild/fill_sample.py)

- L23 `class SampleEvent`
- L33 `SampleEvent.key(self)`
- L37 `load_fill_sample_contract(path: Path | None=None)`
- L42 `event_order(frame: pd.DataFrame)`
- L50 `select_event_keys(contract: dict, events: pd.DataFrame)`
- L70 `next_event_map(events: pd.DataFrame)`
- L85 `replay_until_for_event(*, signal_date: int, confirmed_d0s: list[int], calendar: list[int], next_signal: Optional[int], policy: RebuildPolicy | None=None, repair_observation_sessions: int=10)`
- L116 `load_parent_risk_contract(fill_contract: dict)`
- L121 `independent_wait_reason(*, close: float, confirmation_close: float, repair_level: float, signal_avwap: float, natr20: float, structure_ok: Optional[bool], theta_abs: float=0.08, theta_natr: float=1.0, tolerance: float=1e-12)`
- L166 `wait_window_dates(calendar: list[int], d0: int, *, first_offset: int=1, last_offset: int=5)`
- L174 `independent_no_submit_audit(*, spec: dict, calendar: list[int], bars: dict[int, dict], structure_series: dict[int, dict], avwap: dict[int, float], next_signal: Optional[int], as_of: Optional[int])`
- L258 `path_coverage(results: list[dict], fills: list[dict], risk_decisions: list[dict] | None=None, orders: list[dict] | None=None, attempts: list[dict] | None=None, test_evidence: dict | None=None)`

## sector_panic/rebuild/p1_loss_diagnostic.py

[打开文件](../../sector_panic/rebuild/p1_loss_diagnostic.py)

- L39 `class DiagnosticError`
- L40 `DiagnosticError.__init__(self, code: str, message: str)`
- L47 `class ValidationResult`
- L52 `_prec()`
- L56 `_dec(value)`
- L64 `core_key(row: dict)`
- L73 `event_key(row: dict)`
- L77 `reject_input_name(name: str)`
- L83 `calendar_index(calendar: Iterable[int])`
- L88 `session_distance(index: dict[int, int], start, end)`
- L98 `holding_bucket(sessions: Optional[int])`
- L112 `median_decimal(values: list[Decimal])`
- L122 `format_decimal(value: Decimal)`
- L126 `changed_input_names(before: dict[str, str], after: dict[str, str])`
- L132 `to_jsonable(value)`
- L151 `feature_catalog()`
- L212 `_frame(rows: list[dict])`
- L220 `accounting_class(gross: Decimal, net: Decimal)`
- L230 `_order_identity_mismatch(fill: dict, order: dict)`
- L241 `validate_sources(*, candidates: list[dict], orders: list[dict], fills: list[dict], terminals: dict, certified_hashes: dict[str, str], observed_hashes: dict[str, str], manifest_hashes: Optional[dict]=None, review_binding: Optional[dict]=None, hash_specs: Optional[dict]=None, fee_entry: Optional[Decimal]=None, fee_exit: Optional[Decimal]=None, expected_counts: Optional[dict]=None, price_mismatches: Optional[list[dict]]=None, ledger: Optional[pd.DataFrame]=None, attribution: Optional[list[dict]]=None, end_nav: Optional[Decimal]=None, initial_cash: Decimal=Decimal('1'), end_book_flat: Optional[bool]=None, n_sessions: Optional[int]=None, residual_limit: Decimal=Decimal('1e-24'))`
- L455 `_price(prices: dict, code: str, day: int)`
- L471 `_same_float_print(left: Decimal, right: Decimal)`
- L476 `same_adjusted_close(fill_price: Decimal, adjusted: Decimal, listed: Decimal)`
- L493 `_distance(later: Optional[Decimal], earlier: Optional[Decimal])`
- L499 `build_trade_ledger(fills: list[dict], orders: list[dict], candidates: list[dict], calendar: list[int], prices: dict, fee: Decimal, suspend: Optional[set]=None)`
- L625 `build_close_paths(ledger: pd.DataFrame, prices: dict, calendar: list[int], suspend: set, fee: Decimal, horizons: tuple[int, ...]=(1, 3, 5))`
- L770 `classify_loss_paths(ledger: pd.DataFrame, path_summary: pd.DataFrame)`
- L801 `build_dependence_groups(ledger: pd.DataFrame)`
- L848 `_group_rows(ledger: pd.DataFrame, dimension: str)`
- L879 `_field_distribution(ledger: pd.DataFrame, field_name: str)`
- L904 `aggregate_diagnostics(ledger: pd.DataFrame, daily_paths: pd.DataFrame, groups: pd.DataFrame, candidates: list[dict], terminals: dict, *, horizons: tuple[int, ...]=(1, 3, 5), dimensions: Optional[list[str]]=None, pre_submit_fields: Optional[list[str]]=None)`
- L1136 `render_report(result: dict)`
- L1152 `_fmt_stat(value)`
- L1162 `_report_lines(result, accounting, path, concentration, candidates, gross_loss, fee_flip, no_positive, giveback, unknown, largest)`

## sector_panic/rebuild/portfolio_book.py

[打开文件](../../sector_panic/rebuild/portfolio_book.py)

- L21 `_d(value)`
- L27 `frozen_buy_quantity(budget: Decimal, limit: Decimal, fee_ratio: Decimal=P1_ENTRY_COST_RATIO)`
- L35 `class CashBook`
- L40 `CashBook.available_cash(self)`
- L43 `CashBook.nav(self, position_value: Decimal)`
- L49 `class Lot`
- L60 `class WorkingOrder`
- L77 `class PortfolioDataError`
- L80 `PortfolioDataError.__init__(self, reason: str, order_id: str)`
- L86 `class PortfolioStateError`
- L89 `PortfolioStateError.__init__(self, reason: str, order_id: str)`
- L96 `class SessionBar`
- L108 `class BuyApplication`
- L120 `class Decision`
- L132 `class PortfolioBook`
- L139 `PortfolioBook.position_value(self, marks: dict[str, Decimal])`
- L146 `PortfolioBook.name_slots(self)`
- L153 `PortfolioBook.snapshot(self)`
- L161 `PortfolioBook.working_orders(self, *, side: Optional[str]=None, ts_code: Optional[str]=None)`
- L169 `PortfolioBook.plant_lot(self, lot: Lot)`
- L174 `PortfolioBook.plant_working_buy(self, *, sector: str, event_id: str, signal_date: int, ts_code: str, submit_date: int, target_date: int, limit_price: Decimal, budget: Decimal=P1_ORDER_BUDGET, next_event_id: Optional[str]=None)`
- L207 `PortfolioBook.run_session(self, session: int, next_session: int, *, sector_arrivals: Optional[list[tuple[str, str]]]=None, bars: Optional[dict[str, SessionBar]]=None, applications: Optional[list[BuyApplication]]=None, after_expire: Optional[Callable[[], None]]=None, before_evening: Optional[Callable[[], list]]=None, next_session_known: bool=True)`
- L252 `PortfolioBook._arrive(self, session: int, arrivals: list[tuple[str, str]])`
- L276 `PortfolioBook._match_sells(self, session: int, bars: dict[str, SessionBar])`
- L294 `PortfolioBook._match_buys(self, session: int, bars: dict[str, SessionBar])`
- L323 `PortfolioBook._expire_buys(self, session: int)`
- L331 `PortfolioBook._retry_blocked_sells(self, session: int, next_session: int, next_session_known: bool=True)`
- L345 `PortfolioBook._evening(self, session: int, next_session: int, applications: list[BuyApplication])`
- L391 `PortfolioBook._submit_sell(self, lot: Lot, session: int, next_session: int)`
- L410 `PortfolioBook._targets(self, session: int, side: str)`
- L418 `PortfolioBook._new_order(self, **kwargs)`
- L424 `PortfolioBook._record(self, session: int, phase: str, lot: Lot, action: str, reason: str)`
- L437 `_bare(order: WorkingOrder)`
- L444 `_execution_outcome(order: WorkingOrder, bars: dict[str, SessionBar])`

## sector_panic/rebuild/portfolio_driver.py

[打开文件](../../sector_panic/rebuild/portfolio_driver.py)

- L49 `class FrozenCandidate`
- L69 `class OpenRisk`
- L80 `class DailyAccount`
- L94 `class RollbackEvidence`
- L105 `class DriverRun`
- L118 `class PortfolioDriver`
- L119 `PortfolioDriver.__init__(self, *, calendar: list[int], candidates: list[FrozenCandidate], bars: dict[int, dict[str, SessionBar]], initial_cash: Decimal=Decimal('1'), market_data_origin: str='SYNTHETIC', calendar_origin: str='SYNTHETIC_WEEKDAYS', policy: Optional[RebuildPolicy]=None, dated_levels: Optional[dict]=None, progress: Optional[Callable[[int, int, int], None]]=None)`
- L148 `PortfolioDriver.run(self)`
- L226 `PortfolioDriver._finish(self, result: DriverRun)`
- L240 `PortfolioDriver._still_observable(self, cand: FrozenCandidate, asof: int)`
- L256 `PortfolioDriver._key(self, cand: FrozenCandidate)`
- L259 `PortfolioDriver._candidate_lot(self, cand: FrozenCandidate)`
- L267 `PortfolioDriver._candidate_working(self, cand: FrozenCandidate)`
- L274 `PortfolioDriver._update_terminals(self, session: int)`
- L307 `PortfolioDriver._note_entries(self)`
- L312 `PortfolioDriver._arrivals(self, session: int)`
- L319 `PortfolioDriver._applications(self, session: int, day_bars: dict[str, SessionBar])`
- L325 `PortfolioDriver._one_application(self, session: int, cand: FrozenCandidate, day_bars: dict[str, SessionBar])`
- L386 `PortfolioDriver._probe_window(self, session: int, cand: FrozenCandidate, close: float)`
- L400 `PortfolioDriver._reject(self, cand: FrozenCandidate, reason: str)`
- L412 `PortfolioDriver._review_exits(self, session: int, day_bars: dict[str, SessionBar])`
- L457 `PortfolioDriver._sync_new_fills(self, session: int, day_bars: dict[str, SessionBar])`
- L493 `PortfolioDriver._levels(self, cand: FrozenCandidate, session: int)`
- L503 `PortfolioDriver._candidate_for(self, lot)`
- L514 `PortfolioDriver._daily(self, session: int, day_bars: dict[str, SessionBar])`
- L544 `PortfolioDriver._pending_obligations(self)`
- L569 `PortfolioDriver._mark(self, code: str, day_bars: dict[str, SessionBar])`
- L581 `_capture_book(book: PortfolioBook)`
- L594 `_fingerprint(book: PortfolioBook, risk: dict[str, OpenRisk], last_mark: dict[str, Decimal], entered: set[tuple], terminal: dict[tuple, str])`
- L628 `_observable_price(bar: Optional[SessionBar])`
- L637 `_valid_price(price: Optional[Decimal])`

## sector_panic/rebuild/portfolio_full214_real.py

[打开文件](../../sector_panic/rebuild/portfolio_full214_real.py)

- L57 `_bind_runner_sources(hashes: dict)`
- L64 `_manifest(hashes: dict, gates: dict, **extra)`
- L81 `_write(path: Path, payload)`
- L86 `_write_rows(path: Path, rows: list)`
- L97 `_expected_mark(code: str, bar: SessionBar | None, carried: dict[str, Decimal])`
- L115 `_capital_supported(action: str, *, code: str, open_codes: set[str], working_buys: set[str], cash: Decimal, reserve: Decimal)`
- L138 `_apply_submit(code: str, reserve: Decimal, working_buys: set[str])`
- L143 `audit_book(days: list[dict], orders: list[dict], decisions: list[dict], calendar: list[int], bars: dict[int, dict[str, SessionBar]], *, initial_cash: Decimal=Decimal('1'))`
- L292 `_resolves_this_morning(order: dict, session: int)`
- L296 `_match_sort(order: dict)`
- L304 `_audit_result(ok: bool, issues: list[dict], residual: Decimal, counts: Counter)`
- L323 `_orders_from(book, bars)`
- L360 `_decisions_from(book)`
- L371 `_days_from(result)`
- L384 `_gate_template(**overrides)`
- L413 `run()`

## sector_panic/rebuild/portfolio_n6_real.py

[打开文件](../../sector_panic/rebuild/portfolio_n6_real.py)

- L53 `_sha(path: Path)`
- L61 `_json_ready(value)`
- L71 `_write(path: Path, payload)`
- L75 `_finite(value)`
- L83 `_session_bar(raw: dict | None)`
- L101 `_next_identities(panel: Path, as_of: int)`
- L117 `_levels(series: dict)`
- L132 `_candidate(spec: dict, nxt: tuple)`
- L157 `_bars_for(calendar: list[int], codes: list[str], raw_bars: dict)`
- L169 `_dec(value)`
- L173 `_rounded_nav(cash: Decimal, rows: list[tuple[str, Decimal, Decimal]])`
- L186 `_exact_nav(cash: Decimal, rows: list[tuple[str, Decimal, Decimal]])`
- L195 `_reconcile(days: list[dict], orders: list[dict], calendar: list[int])`
- L277 `_family(reason: str)`
- L281 `_old_no_entry_terminal(old: dict)`
- L296 `_no_limit(raw)`
- L300 `_limit_token(side: str, raw)`
- L308 `_compare(old_results: list[dict], old_orders: list[dict], new_orders: list[dict], decisions: list[dict], terminal: dict)`
- L480 `run()`

## sector_panic/rebuild/pytest_plugin.py

[打开文件](../../sector_panic/rebuild/pytest_plugin.py)

- L15 `class RebuildEvidencePlugin`
- L16 `RebuildEvidencePlugin.__init__(self, path: Path)`
- L21 `RebuildEvidencePlugin.pytest_collection_modifyitems(self, items)`
- L40 `RebuildEvidencePlugin.pytest_runtest_makereport(self, item, call)`
- L65 `RebuildEvidencePlugin.pytest_sessionfinish(self, session, exitstatus)`
- L76 `pytest_configure(config)`

## sector_panic/rebuild/risk_inputs.py

[打开文件](../../sector_panic/rebuild/risk_inputs.py)

- L16 `parse_structure_flag(value)`
- L45 `last_valid_mark(bars: dict[int, dict], as_of: int)`
- L64 `_finite_positive(value)`
- L75 `class ConfirmationSnapshot`
- L98 `ConfirmationSnapshot.key(self)`
- L101 `ConfirmationSnapshot.ready_for_hold(self)`
- L112 `ConfirmationSnapshot.to_dict(self)`
- L138 `structure_ok_map(series: dict[int, dict])`
- L150 `validate_structure_series(series: dict[int, dict], *, key: tuple)`
- L171 `validate_stop_rule(stop_distance: float, stop_mode: str, stop_level)`
- L192 `build_structure_row(*, date: int, d0: int, calendar: list[int], bar: dict | None, snapshot: ConfirmationSnapshot, avwap, previous: dict | None, earliest_review_offset: int=1, earliest_fill_offset: int=2, last_target_offset: int=5)`
- L282 `generate_structure_series(*, snapshot: ConfirmationSnapshot, calendar: list[int], bars: dict[int, dict], avwap: dict[int, float], as_of: Optional[int], earliest_review_offset: int=1, earliest_fill_offset: int=2, last_target_offset: int=5)`

## sector_panic/rebuild/risk_policy.py

[打开文件](../../sector_panic/rebuild/risk_policy.py)

- L25 `class StructureEval`
- L33 `StructureEval.as_flag_dict(self)`
- L44 `_finite_positive(value)`
- L54 `stop_distance_from_natr(natr20: float, *, floor: float=STOP_FLOOR_RATIO, multiple: float=STOP_NATR_MULTIPLE)`
- L71 `validate_stop_distance(distance: float)`
- L83 `stop_level_from_fill(entry_price: float, stop_distance: float)`
- L93 `stop_hit(close: float, entry_price: float, stop_distance: float, *, tolerance: float=1e-12)`
- L110 `evaluate_structure(close: float, higher_low_low: float, panic_low: float, repair_level: float, signal_avwap: float)`
- L150 `primary_exit_reason(*, working_sell: bool, stop_hit_flag: bool, new_event: bool, structure_broken: bool, max_hold: bool, existing_intent: Optional[str]=None)`
- L178 `calendar_position(calendar: list[int])`
- L194 `structure_phase(date: int, d0: int, calendar: list[int], *, earliest_review_offset: int=1, earliest_fill_offset: int=2, last_target_offset: int=5)`
- L232 `compute_signal_natr20(ohlc: dict[int, dict], calendar: list[int], signal_date: int, observations: int=20)`

## sector_panic/rebuild/run_evidence.py

[打开文件](../../sector_panic/rebuild/run_evidence.py)

- L53 `_sha_path(path: Path)`
- L59 `execution_source_manifest(root: Path | None=None)`
- L85 `frozen_strategy_issues(contract: dict)`
- L114 `load_expected_keys_csv(contract: dict)`
- L151 `_recompute_replay_until(calendar: list[int], signal_date: int, confirmed_d0s: list[int])`
- L165 `preflight_contract(contract: dict, *, contract_path: Path | None=None)`
- L259 `resolved_contract_payload(contract: dict, preflight: dict)`

## sector_panic/rebuild/verification.py

[打开文件](../../sector_panic/rebuild/verification.py)

- L26 `load_acceptance_plan()`
- L30 `acceptance_ids(level: str | None=None)`
- L37 `mutation_specs()`
- L41 `write_json(path: Path, obj: Any)`
- L46 `content_hash(obj: Any)`
- L51 `gate_row(test_id: str, expected: str, observed: Any, status: str, evidence: str='')`
- L64 `preflight(out_root: Path | None=None)`
- L81 `collect_pytest_acceptance_ids(items)`
- L102 `implementation_hash(root: Path | None=None)`
- L119 `load_evidence_report(path: str | Path)`
- L130 `_tests_in_report(evidence: dict)`
- L139 `load_rebuild_test_nodeids(root: Path | None=None)`
- L154 `load_acceptance_nodeid_catalog(root: Path | None=None)`
- L185 `_normalize_nodeid(nodeid: str)`
- L189 `nodeid_bound_to_id(test_id: str, nodeid: str, catalog: dict[str, list[str]])`
- L199 `_phase_ok(value: object)`
- L203 `executed_record_status(rec: dict | None, expected_hash: str)`
- L239 `shadow_blocked_without_evidence(scope: dict | None=None)`
- L249 `research_evidence_ok(research_evidence: dict | None)`
- L260 `_row_from_report_test(tid: str, nodeid: str, test: dict | None, expected_hash: str, evidence: dict)`
- L277 `verify_structured_report(level: str, evidence: dict, run_id: str, out_root: Path, *, research_evidence: dict | None=None)`
- L372 `verify_level(level: str, collected_ids: set[str], run_id: str, out_root: Path, *, executed: dict | None=None, research_evidence: dict | None=None, evidence_report: Path | dict | None=None)`

## sector_panic/regime.py

[打开文件](../../sector_panic/regime.py)

- L56 `class ShockSource`
- L64 `class TrendState`
- L72 `class RegimeClassification`
- L85 `RegimeClassification.__post_init__(self)`
- L94 `_validate_index_frame(index_df: pd.DataFrame, name: str)`
- L128 `_ret_5d_series(closes: np.ndarray)`
- L137 `_rolling_quantile_of_rets(rets_5d: np.ndarray, window: int, min_periods: int, quantile: float)`
- L164 `_rolling_beta_series(sector_ret_1d: np.ndarray, market_ret_1d: np.ndarray, window: int, min_periods: int)`
- L196 `_rolling_quantile_of_residuals(residual_5d: np.ndarray, window: int, min_periods: int, quantile: float)`
- L208 `compute_regime(market_index: pd.DataFrame, sector_index: pd.DataFrame, signal_date: int, trade_days: set | None=None)`
- L410 `compute_regime_series(market_index: pd.DataFrame, sector_index: pd.DataFrame, dates: list[int] | None=None, trade_days: set | None=None)`
- L550 `_load_exchange_trade_days()`
- L573 `_compute_trend(closes: np.ndarray)`

## sector_panic/repair_quality_r7.py

[打开文件](../../sector_panic/repair_quality_r7.py)

- L18 `_columns(frame: pd.DataFrame, names: Iterable[str])`
- L22 `_bool_series(frame: pd.DataFrame, column: str, default: bool=False)`
- L28 `_json_counts(values: pd.Series)`
- L33 `build_uplift_decomposition(components: pd.DataFrame, event_results: pd.DataFrame, q0_rule_id: str, q2_rule_id: str)`
- L113 `uplift_decomposition_integrity(decomposition: pd.DataFrame, event_results: pd.DataFrame, q0_rule_id: str, q2_rule_id: str, tolerance: float=1e-12)`
- L142 `build_stock_level_panel(selection: pd.DataFrame, e2_confirmations: pd.DataFrame, q1_confirmations: pd.DataFrame, q2_eligibility: pd.DataFrame, preentry: pd.DataFrame, postpath: pd.DataFrame, components: pd.DataFrame, attempts: pd.DataFrame, event_results: pd.DataFrame, q2_breadth: pd.DataFrame, rule_labels: dict[str, str], rd2_status: str)`
- L298 `build_event_level_panel(source_events: pd.DataFrame, selection: pd.DataFrame, event_results: pd.DataFrame, components: pd.DataFrame, stock_panel: pd.DataFrame, q2_breadth: pd.DataFrame, rule_labels: dict[str, str], rd2_status: str)`
- L400 `build_episode_level_panel(event_panel: pd.DataFrame, macro_episodes: pd.DataFrame)`
- L443 `episode_inference(event_panel: pd.DataFrame, seed: int, runs: int)`
- L491 `_bh_qvalues(pvalues: pd.Series)`
- L504 `build_feature_quartile_statistics(stock_panel: pd.DataFrame, decomposition: pd.DataFrame, features: list[str], ordered_episode_ids: list[str], seed: int, runs: int)`

## sector_panic/structural_feasibility.py

[打开文件](../../sector_panic/structural_feasibility.py)

- L23 `class BasketPolicy`
- L32 `normalize_calendar(values: Iterable[int])`
- L39 `_normalize_dates(frame: pd.DataFrame, date_column: str='trade_date')`
- L47 `_require_unique(frame: pd.DataFrame, keys: list[str], label: str)`
- L52 `build_diagnostic_panel(prices: pd.DataFrame, limit_status: pd.DataFrame, suspend_status: pd.DataFrame, stock_status: pd.DataFrame, namechange: pd.DataFrame, calendar: Iterable[int], amount_multiplier: float=1.0)`
- L197 `build_signal_diagnostics(universe: pd.DataFrame, panel: pd.DataFrame, sector_index: pd.DataFrame, calendar: Iterable[int], signal_config: dict)`
- L288 `_panel_lookup(panel: pd.DataFrame)`
- L292 `_row_or_none(lookup: pd.DataFrame, code: str, trade_date: int)`
- L302 `_return_for_codes(lookup: pd.DataFrame, codes: list[str], entry_date: int, target_date: int, minimum_coverage: float)`
- L328 `_operational_return_for_fills(lookup: pd.DataFrame, filled_codes: list[str], selected_count: int, entry_date: int, target_date: int)`
- L349 `_decision_path(lookup: pd.DataFrame, codes: list[str], dates: np.ndarray)`
- L374 `_trail_diagnostic(ratios: np.ndarray, dates: np.ndarray, stop_loss: float, activation: float, trail: float, scan_limit: int)`
- L411 `_stop_realizability(lookup: pd.DataFrame, codes: list[str], selected_count: int, dates: np.ndarray, ratios: np.ndarray, stop_loss: float, decision_cost_bps: int)`
- L509 `diagnose_event_baskets(sector: str, events: pd.DataFrame, universe: pd.DataFrame, panel: pd.DataFrame, sector_index: pd.DataFrame, calendar: Iterable[int], policy: BasketPolicy, execution_config: dict, horizons: Iterable[int]=CAPTURE_HORIZONS)`
- L771 `assign_macro_episodes(events: pd.DataFrame, calendar: Iterable[int], holding_sessions: int=20)`

## sector_panic/t0_cluster_duration_predictor.py

[打开文件](../../sector_panic/t0_cluster_duration_predictor.py)

- L67 `_require(frame: pd.DataFrame, columns: set[str], label: str)`
- L73 `consecutive_down_days(closes: pd.Series, signal_date: int)`
- L103 `window_depth_percentile(closes: pd.Series, signal_date: int, window: int=WINDOW_SESSIONS, history: int=QUANTILE_WINDOW, min_periods: int=QUANTILE_MIN_PERIODS)`
- L125 `predicted_single_mask(features: pd.DataFrame, combination_id: str)`
- L140 `cluster_duration_labels(signal_daily: pd.DataFrame, calendar: np.ndarray, gap_sessions: int=5)`
- L173 `_index_close_map(index_daily: pd.DataFrame, code: str)`
- L180 `enrich_panel_returns(panel: pd.DataFrame)`
- L208 `t0_basket_features(universe: pd.DataFrame, panel: pd.DataFrame, signal_date: int)`
- L261 `t0_index_features(sector_close: pd.Series, parent_close: pd.Series, signal_date: int)`
- L312 `attach_score_components(row: dict)`
- L334 `selected_path_return(selected_codes: list[str], panel: pd.DataFrame, calendar: np.ndarray, signal_date: int, start_offset: int, end_offset: int)`
- L369 `build_feature_ledger(events: pd.DataFrame, sector_features: dict[tuple[str, int], dict])`
- L396 `join_labels(features: pd.DataFrame, duration: pd.DataFrame, paths: pd.DataFrame, controls: pd.DataFrame)`
- L415 `_episode_equal_mean(frame: pd.DataFrame, column: str)`
- L426 `evaluate_combination(labeled: pd.DataFrame, combination_id: str)`
- L463 `combination_gates(metrics: dict)`
- L494 `adjudicate(combination_metrics: list[dict])`
- L508 `univariate_split(labeled: pd.DataFrame)`
- L532 `episode_summary(labeled: pd.DataFrame)`

## sector_panic/t0_mechanism_quintiles.py

[打开文件](../../sector_panic/t0_mechanism_quintiles.py)

- L67 `concentration_ratio(sector_close: pd.Series, signal_date: int)`
- L95 `intraday_seal_features(prices_raw: pd.DataFrame, limits_raw: pd.DataFrame, panel: pd.DataFrame, active_codes_set: set[str], signal_date: int)`
- L157 `l2_labels(events: pd.DataFrame, signal_daily: pd.DataFrame, calendar: np.ndarray)`
- L192 `_basket_names_by_event(selection: pd.DataFrame)`
- L201 `l3_l4_labels(events: pd.DataFrame, selection: pd.DataFrame, packed: dict, calendar: np.ndarray)`
- L266 `_bin_metrics(group: pd.DataFrame)`
- L287 `streak_bin_table(labeled: pd.DataFrame)`
- L300 `_feature_quintile(series: pd.Series, quintiles: int=5)`
- L315 `quintile_tables(labeled: pd.DataFrame, features: Sequence[str]=QUINTILE_FEATURES)`
- L343 `shock_source_table(labeled: pd.DataFrame)`
- L364 `c1_interaction_contrast(labeled: pd.DataFrame)`

## sector_panic/v10_action_value_dataset.py

[打开文件](../../sector_panic/v10_action_value_dataset.py)

- L39 `_bool(value: object)`
- L45 `_key_tuple(row: pd.Series | dict)`
- L50 `structural_barrier_b_t(*, higher_low_low: float, panic_low: float, repair_level: float, signal_avwap: float, natr20: float, dual_buffer_natr: float=DUAL_BUFFER_NATR)`
- L78 `structural_margin_natr(*, close_t: float, higher_low_low: float, panic_low: float, repair_level: float, signal_avwap: float, natr20: float, dual_buffer_natr: float=DUAL_BUFFER_NATR)`
- L103 `atomic_structure_failed(*, close_t: float, higher_low_low: float, panic_low: float, repair_level: float, signal_avwap: float, natr20: float, dual_buffer_natr: float=DUAL_BUFFER_NATR)`
- L126 `verify_bt_equals_atomic_or(*, close_t: float, higher_low_low: float, panic_low: float, repair_level: float, signal_avwap: float, natr20: float, hard_higher_low_failure: bool, hard_panic_low_failure: bool, buffered_dual_anchor_failure: bool, dual_buffer_natr: float=DUAL_BUFFER_NATR)`
- L154 `remaining_fixed_hold_fraction(holding_session_t: float, maximum_holding_sessions: int=MAX_HOLD)`
- L164 `_parent_first_sell_decision(attempts: pd.DataFrame)`
- L172 `_filled_buy_row(attempts: pd.DataFrame)`
- L183 `_filled_parent_sell_row(attempts: pd.DataFrame)`
- L192 `_next_date(calendar: np.ndarray, date: int)`
- L200 `build_decisions(v12_daily: pd.DataFrame, *, parent_components: pd.DataFrame, parent_attempts: pd.DataFrame, baseline_rule_id: str=V10_RULE_ID)`
- L312 `build_features(decisions: pd.DataFrame, *, v10_daily: pd.DataFrame, v10_anchor: pd.DataFrame, parent_components: pd.DataFrame, baseline_rule_id: str=V10_RULE_ID, dual_buffer_natr: float=DUAL_BUFFER_NATR, maximum_holding_sessions: int=MAX_HOLD, numerical_tolerance: float=TOL)`
- L454 `simulate_full_exit_fill(*, ts_code: str, trigger_date: int, parent_flat_date: int, panel: pd.DataFrame, calendar: Iterable[int])`
- L500 `_panel_sell_status(panel: pd.DataFrame, *, ts_code: str, trade_date: int)`
- L510 `y_full_from_prices(*, quantity: float, early_sell_price: float, parent_sell_price: float, exit_cost_ratio: float, target_budget: float)`
- L527 `build_action_labels(decisions: pd.DataFrame, *, parent_components: pd.DataFrame, parent_attempts: pd.DataFrame, panels: dict[str, pd.DataFrame], calendar: Iterable[int], baseline_rule_id: str=V10_RULE_ID, policy: H1Policy | None=None, cross_check_h1: bool=True)`
- L782 `assert_feature_causality(features: pd.DataFrame, *, mutated_future_prices: pd.DataFrame | None=None)`

## sector_panic/v10_action_value_model.py

[打开文件](../../sector_panic/v10_action_value_model.py)

- L18 `class SplitBlock`
- L31 `_bool(value: object)`
- L37 `_finite(value: object)`
- L45 `episode_start_map(events: pd.DataFrame)`
- L66 `assign_episode_splits(*, events: pd.DataFrame, labels: pd.DataFrame, parent_components: pd.DataFrame | None=None, blocks: Iterable[SplitBlock]=DEFAULT_BLOCKS)`
- L174 `equal_episode_trigger_weights(frame: pd.DataFrame)`
- L189 `_weighted_mean(values: np.ndarray, weights: np.ndarray)`
- L195 `_weighted_population_std(values: np.ndarray, weights: np.ndarray, mean: float)`
- L202 `standardize_train(x: np.ndarray, weights: np.ndarray)`
- L232 `apply_standardize(x: np.ndarray, means: np.ndarray, scales: np.ndarray)`
- L240 `fit_ridge_svd(z: np.ndarray, y: np.ndarray, weights: np.ndarray, *, alpha: float=1.0, fit_intercept: bool=True)`
- L277 `fit_block_models(*, features: pd.DataFrame, labels: pd.DataFrame, split_assignment: pd.DataFrame, block_id: str, alpha: float=1.0)`
- L436 `_episode_series(frame: pd.DataFrame)`
- L443 `coverage_ok(*, features: pd.DataFrame, labels: pd.DataFrame, split_assignment: pd.DataFrame, blocks: Iterable[SplitBlock]=DEFAULT_BLOCKS, min_train_eligible: int=30, min_train_episodes: int=8, min_validate_eligible: int=15, min_validate_episodes: int=5, min_combined_validate_episodes: int=10)`

## sector_panic/v10_delayed_structure_path_check.py

[打开文件](../../sector_panic/v10_delayed_structure_path_check.py)

- L37 `_key_tuple(row: pd.Series | dict)`
- L42 `_atomic_structure_failed(row: pd.Series | dict)`
- L51 `classify_delta(delta: float, *, tol: float=TOL)`
- L62 `observation_index(path: pd.DataFrame, trigger_date: int, k: int)`
- L77 `_component_path(frame: pd.DataFrame, key: tuple[str, str, str])`
- L85 `_row_on_date(frame: pd.DataFrame, key: tuple[str, str, str], trade_date: int)`
- L97 `_margin_from_rows(*, daily_row: pd.Series | None, anchor_row: pd.Series | None, natr20: float, dual_buffer_natr: float=DUAL_BUFFER_NATR)`
- L118 `_binding_leg(daily_row: pd.Series | None, anchor_row: pd.Series | None, natr20: float)`
- L141 `assign_validation_roles(*, events: pd.DataFrame, rows: pd.DataFrame, blocks: Iterable[SplitBlock]=DEFAULT_BLOCKS)`
- L179 `build_delayed_observations(*, triggers: pd.DataFrame, parent_components: pd.DataFrame, parent_attempts: pd.DataFrame, v10_daily: pd.DataFrame, v10_anchor: pd.DataFrame, v12_daily: pd.DataFrame, panels: dict[str, pd.DataFrame], calendar: Iterable[int], k_values: tuple[int, ...]=(PRIMARY_K, SENSITIVITY_K), baseline_rule_id: str=V10_RULE_ID, policy: H1Policy | None=None, dual_buffer_natr: float=DUAL_BUFFER_NATR, numerical_tolerance: float=TOL)`
- L445 `_median(values: pd.Series)`
- L452 `evaluate_k(observations: pd.DataFrame, *, k: int, min_validate_eligible: int=15, min_validate_episodes: int=5, min_combined_validate_episodes: int=10, min_group_combined: int=8, min_group_block: int=5, numerical_tolerance: float=TOL)`
- L610 `primary_disposition(results: dict[int, dict])`

## sector_panic/v10_h1_mech_half.py

[打开文件](../../sector_panic/v10_h1_mech_half.py)

- L33 `class H1Policy`
- L40 `H1Policy.validate(self)`
- L48 `H1Policy.doubled(self)`
- L58 `_bool(value: object)`
- L64 `_first_rows(frame: pd.DataFrame)`
- L82 `build_trigger_ledger(v12_daily: pd.DataFrame)`
- L106 `_filled_buy(attempts: pd.DataFrame)`
- L117 `_filled_parent_sell(attempts: pd.DataFrame)`
- L126 `_next_date(calendar: np.ndarray, date: int)`
- L134 `replay_component(parent_component: pd.Series | dict, parent_daily: pd.DataFrame, parent_attempts: pd.DataFrame, trigger: pd.Series | dict | None, *, panel: pd.DataFrame, calendar: Iterable[int], policy: H1Policy | None=None, candidate_rule_id: str=H1_RULE_ID)`
- L298 `aggregate_h1_events(components: pd.DataFrame)`

## sector_panic/v10_max_hold_path_diagnostic.py

[打开文件](../../sector_panic/v10_max_hold_path_diagnostic.py)

- L41 `class MaxHoldPathPolicy`
- L49 `MaxHoldPathPolicy.validate(self)`
- L60 `_number(value)`
- L68 `_bool(value)`
- L74 `_require_columns(frame: pd.DataFrame, columns: set[str], name: str)`
- L80 `round_trip_net_return(decision_return: float, entry_cost_ratio: float, exit_cost_ratio: float)`
- L98 `_path_lookup(daily: pd.DataFrame)`
- L109 `analyze_filled_path(component: dict, daily: pd.DataFrame, policy: MaxHoldPathPolicy | None=None)`
- L193 `_primary_filled(components: pd.DataFrame, policy: MaxHoldPathPolicy)`
- L202 `build_component_path_ledger(components: pd.DataFrame, daily: pd.DataFrame, policy: MaxHoldPathPolicy | None=None, events: pd.DataFrame | None=None)`
- L235 `summarize_exit_reasons(path_ledger: pd.DataFrame)`
- L256 `summarize_early_exits(path_ledger: pd.DataFrame, *, reason: str='MAX_HOLD_20D', sessions: Iterable[int]=EARLY_SESSIONS)`
- L290 `interpret_max_hold(exit_summary: pd.DataFrame, early_summary: pd.DataFrame)`
- L342 `build_diagnostic_outputs(components: pd.DataFrame, daily: pd.DataFrame, policy: MaxHoldPathPolicy | None=None, events: pd.DataFrame | None=None)`

## sector_panic/v10_selective_exit_replay.py

[打开文件](../../sector_panic/v10_selective_exit_replay.py)

- L24 `_bool(value: object)`
- L30 `_finite(value: object)`
- L38 `selection_trigger_map(decisions: pd.DataFrame, *, selected_keys: set[tuple[str, str, str]] | None, select_all_eligible: bool=False)`
- L63 `replay_selected_half(*, parent_components: pd.DataFrame, parent_daily: pd.DataFrame, parent_attempts: pd.DataFrame, decisions: pd.DataFrame, panels: dict[str, pd.DataFrame], calendar: Iterable[int], parent_rule_id: str, candidate_rule_id: str, policy: H1Policy, selected_keys: set[tuple[str, str, str]] | None=None, select_all_eligible: bool=False)`
- L126 `attach_episode_id(events: pd.DataFrame, control_events: pd.DataFrame)`
- L135 `paired_event_uplift(candidate_events: pd.DataFrame, control_events: pd.DataFrame)`
- L170 `summarize_paired(pair: pd.DataFrame, *, validate_event_keys: set[tuple[str, str]] | None=None, require_finite: bool=True)`
- L218 `episode_bootstrap_event_mean(pair: pd.DataFrame, *, seed: int=20260909, runs: int=5000)`
- L244 `leave_one_episode_out(pair: pd.DataFrame)`
- L260 `action_diagnostics(*, labels: pd.DataFrame, selected_keys: set[tuple[str, str, str]], eligible_mask: pd.Series)`
- L303 `run_policy_arms(*, parent_components: pd.DataFrame, parent_daily: pd.DataFrame, parent_attempts: pd.DataFrame, control_events: pd.DataFrame, decisions: pd.DataFrame, predictions: pd.DataFrame, panels: dict[str, pd.DataFrame], calendar: Iterable[int], baseline_rule_id: str=V10_RULE_ID, p3_rule_id: str, p2_rule_id: str, p1_rule_id: str, policy: H1Policy | None=None)`

## sector_panic/v11_confirmation_invalidation.py

[打开文件](../../sector_panic/v11_confirmation_invalidation.py)

- L15 `_bool(series: pd.Series)`
- L19 `_ymd(series: pd.Series)`
- L24 `frozen_max_hold_winners(v10_components: pd.DataFrame, *, rule_id: str=V10_CONFIRM_CLOSE_FLOOR_RULE_ID)`
- L44 `winner_max_hold_retention(v10_components: pd.DataFrame, v11_components: pd.DataFrame, *, denominator_count: int=88, kill_if_numerator_ge: int=9)`

## sector_panic/v12_evidence_stack.py

[打开文件](../../sector_panic/v12_evidence_stack.py)

- L99 `class EvidenceStackPolicy`
- L107 `EvidenceStackPolicy.validate(self)`
- L118 `_bool(value)`
- L126 `_number(value)`
- L134 `_int_or_nan(value)`
- L139 `_require_columns(frame: pd.DataFrame, columns: set[str], name: str)`
- L145 `next_event_boundaries(events: pd.DataFrame, calendar: np.ndarray)`
- L161 `scheduled_exit_boundary(entry_date: int, next_boundary_date: int | None, calendar: np.ndarray, *, maximum_holding_sessions: int=MAXIMUM_HOLDING_SESSIONS)`
- L184 `true_range_ratio(high, low, prev_close)`
- L196 `strong_disprove_candidate(*, in_watch: bool, close_below_repair: bool, stop_trigger: bool, holding_session: int, scheduled_boundary_session: int, suspended: bool)`
- L215 `classify_unresolved_component(*, v11_unresolved: bool, v10_unresolved: bool, v10_flat_date, v11_last_sell_date, v11_last_sell_status: str | None, v10_fill_date, runtime_end_date)`
- L250 `_primary_filled(components: pd.DataFrame, policy: EvidenceStackPolicy)`
- L261 `_attach_labels(filled: pd.DataFrame, v11_components: pd.DataFrame, policy: EvidenceStackPolicy)`
- L308 `build_session_features(daily_rows: list[dict], *, confirmation_close: float, entry_price: float, natr20: float, scheduled_boundary_session: int, suspend_dates: set[int], range_by_date: dict[int, float])`
- L417 `_price_lookup(prices: pd.DataFrame, codes: set[str])`
- L433 `_suspend_dates(suspend: pd.DataFrame, codes: set[str])`
- L447 `_last_sell(attempts: pd.DataFrame, rule_id: str)`
- L464 `build_unresolved_audit(v10_components: pd.DataFrame, v11_components: pd.DataFrame, v10_attempts: pd.DataFrame, v11_attempts: pd.DataFrame, *, runtime_end_date: int, policy: EvidenceStackPolicy | None=None)`
- L552 `build_daily_ledger(v10_components: pd.DataFrame, v10_daily: pd.DataFrame, v10_events: pd.DataFrame, v11_components: pd.DataFrame, *, calendar: np.ndarray, prices: pd.DataFrame, suspend: pd.DataFrame, policy: EvidenceStackPolicy | None=None)`
- L637 `build_fill_summary(daily: pd.DataFrame)`
- L676 `descriptive_counts(summary: pd.DataFrame, events: pd.DataFrame | None=None)`
- L711 `build_episode_diagnostic(daily: pd.DataFrame, fill_summary: pd.DataFrame, events: pd.DataFrame)`
- L845 `features_ignore_labels(daily_rows: list[dict], **kwargs)`

## sector_panic/v12_r1_integrity.py

[打开文件](../../sector_panic/v12_r1_integrity.py)

- L34 `_bool(value: object)`
- L40 `_finite(value: object)`
- L48 `_present(value: object)`
- L52 `validate_component_result(result: Mapping[str, pd.DataFrame], *, calendar: Iterable[int], tolerance: float=1e-10)`
- L315 `build_event_daily(component_daily: pd.DataFrame, *, components: pd.DataFrame, capital: float=1.0, tolerance: float=1e-10)`
- L503 `build_event_closure_ledger(components: pd.DataFrame, event_daily: pd.DataFrame)`
- L541 `_execution_attempts_with_empty_event_groups(attempts: pd.DataFrame, event_daily: pd.DataFrame)`
- L584 `validate_batch_closure(*, components: pd.DataFrame, attempts: pd.DataFrame, inventory: pd.DataFrame, daily: pd.DataFrame, event_ledger: pd.DataFrame, event_daily: pd.DataFrame, states: pd.DataFrame, anchors: pd.DataFrame, calendar: Iterable[int], normalized_event_capital: float=1.0)`
- L620 `compare_declared_output_bytes(left: str | Path, right: str | Path, declared: Iterable[str])`

## sector_panic/v13_forward_marker.py

[打开文件](../../sector_panic/v13_forward_marker.py)

- L55 `class ForwardMarkerError`
- L59 `_date8(value: object, field: str)`
- L75 `_workspace_path(value: object, *, field: str)`
- L86 `_require_exact(mapping: dict, field: str, expected: object, *, section: str)`
- L107 `first_open_session_after(calendar: Iterable[object], freeze_date: object)`
- L132 `class ForwardMarker`
- L148 `ForwardMarker.historical_return_evaluation(self)`
- L152 `ForwardMarker.live_trading_approved(self)`
- L155 `ForwardMarker.is_eligible(self, signal_date: object)`
- L159 `ForwardMarker.assert_signal_date(self, signal_date: object, *, field: str='signal_date')`
- L168 `ForwardMarker.assert_forward_frame(self, frame: pd.DataFrame, *, date_column: str='signal_date')`
- L196 `ForwardMarker.select_forward_frame(self, frame: pd.DataFrame, *, date_column: str='signal_date', end_date: object | None=None)`
- L220 `_validate_scope(raw: dict, *, scope_path: Path)`
- L400 `load_scope(path: str | Path=DEFAULT_SCOPE)`
- L416 `load_marker(path: str | Path=DEFAULT_SCOPE)`
- L421 `validate_scope(scope: dict, *, scope_path: str | Path=DEFAULT_SCOPE)`
- L430 `assert_forward_only(frame: pd.DataFrame, marker: ForwardMarker, *, date_column: str='signal_date')`
- L440 `filter_forward_events(frame: pd.DataFrame, marker: ForwardMarker, *, date_column: str='signal_date', end_date: object | None=None)`
- L451 `_is_descendant(path: Path, parent: Path)`
- L459 `assert_safe_forward_output(path: str | Path)`
- L482 `marker_payload(marker: ForwardMarker)`

## sector_panic/v14_confirmation_floor_epsilon.py

[打开文件](../../sector_panic/v14_confirmation_floor_epsilon.py)

- L29 `class ConfirmationFloorDecision`
- L38 `ConfirmationFloorDecision.__post_init__(self)`
- L56 `_finite_positive(value: object)`
- L63 `confirmation_epsilon_floor(confirmation_close: object, natr20: object, *, epsilon_natr: float=EPSILON_NATR)`
- L82 `evaluate_confirmation_floor_fill(*, close: object, confirmation_close: object, natr20: object, numerical_tolerance: float=NUMERICAL_TOLERANCE, epsilon_natr: float=EPSILON_NATR)`

## sector_panic/v14_forward_marker.py

[打开文件](../../sector_panic/v14_forward_marker.py)

- L55 `_require_exact(mapping: dict, field: str, expected: object, *, section: str)`
- L70 `_workspace_path(value: object, *, field: str)`
- L81 `_is_descendant(path: Path, parent: Path)`
- L89 `assert_safe_forward_output(path: str | Path)`
- L114 `class V14ForwardMarker`
- L128 `V14ForwardMarker.historical_return_evaluation(self)`
- L132 `V14ForwardMarker.live_trading_approved(self)`
- L135 `V14ForwardMarker.assert_signal_date(self, signal_date: object, *, field: str='signal_date')`
- L144 `V14ForwardMarker.assert_forward_frame(self, frame: pd.DataFrame, *, date_column: str='signal_date')`
- L163 `_validate_scope(raw: dict, *, scope_path: Path)`
- L324 `load_scope(path: str | Path=DEFAULT_SCOPE)`
- L337 `load_marker(path: str | Path=DEFAULT_SCOPE)`
- L341 `validate_scope(scope: dict, *, scope_path: str | Path=DEFAULT_SCOPE)`
- L349 `marker_payload(marker: V14ForwardMarker)`

## sector_panic/verify_golden.py

[打开文件](../../sector_panic/verify_golden.py)

- L57 `_is_dynamic_shadow_artifact(relative_path: str)`
- L64 `sha256_file(path: Path)`
- L77 `_tracked_source_files(root: Path)`
- L97 `_untracked_code_files(root: Path)`
- L124 `git_state(root: Path)`
- L157 `verify_golden(baseline: dict, root: Path=ROOT, baseline_path: Path | None=None)`
- L358 `amend_baseline(reason: str, root: Path=ROOT, baseline_path: Path=BASELINE_PATH)`
- L482 `main(argv: list[str] | None=None)`

## tests/__init__.py

[打开文件](../../tests/__init__.py)

无顶层函数/类；阅读模块常量、导入或入口逻辑。

## tests/sector_panic_rebuild/__init__.py

[打开文件](../../tests/sector_panic_rebuild/__init__.py)

无顶层函数/类；阅读模块常量、导入或入口逻辑。

## tests/sector_panic_rebuild/conftest.py

[打开文件](../../tests/sector_panic_rebuild/conftest.py)

- L18 `calendar(n: int=40)`
- L22 `bars(cal: list[int], close: float=101.0, overrides: dict | None=None)`
- L38 `cal()`
- L43 `d0(cal)`
- L48 `policy()`
- L52 `make_engine(cal, d0, overrides=None, close=101.0, cfg_kw=None, n=None)`

## tests/sector_panic_rebuild/oracle.py

[打开文件](../../tests/sector_panic_rebuild/oracle.py)

- L9 `D(x)`
- L13 `cash_end(cash_start, buy_notional=0, buy_fees=0, sell_notional=0, sell_fees=0, cash_actions=0, external_flows=0)`
- L21 `shares_end(shares_start, bought=0, sold=0, share_actions=0)`
- L25 `nav(cash, shares, mark, receivables=0)`
- L29 `round_fen(x)`
- L33 `preset_qty(budget, limit, fee_ratio)`
- L37 `stop_distance(natr20, floor=0.05, multiple=2.5)`
- L43 `stop_level(entry_price, distance)`
- L47 `stop_hit(close, entry_price, distance, tolerance=0)`
- L52 `structure_flags(close, higher_low_low, panic_low, repair_level, avwap)`

## tests/sector_panic_rebuild/test_cash_reconciliation.py

[打开文件](../../tests/sector_panic_rebuild/test_cash_reconciliation.py)

- L21 `test_cash_01_independent_decimal_oracle()`
- L38 `test_cash_02_costs_once_frozen_not_double_counted()`
- L54 `test_cash_03_permutation_and_scale_invariance()`

## tests/sector_panic_rebuild/test_causal_orders.py

[打开文件](../../tests/sector_panic_rebuild/test_causal_orders.py)

- L13 `test_time_01_future_price_does_not_change_past_orders()`
- L27 `test_time_02_below_c_still_fills_above_limit_does_not()`
- L49 `test_time_03_no_same_day_exit()`
- L65 `test_time_04_future_event_does_not_rewrite_orders()`
- L83 `test_order_01_cap_not_raised_by_c()`
- L111 `test_order_02_quantity_frozen_cheaper_fill_leaves_cash()`
- L141 `test_order_03_clock_offsets()`

## tests/sector_panic_rebuild/test_contracts_and_governance.py

[打开文件](../../tests/sector_panic_rebuild/test_contracts_and_governance.py)

- L24 `test_gov_01_legacy_hashes_and_fresh_dir()`
- L49 `test_gov_02_legacy_source_unavailable()`
- L60 `test_gov_03_manifest_identity()`
- L81 `test_state_01_data_failure_not_cash()`
- L89 `test_state_02_right_censored_pending()`
- L100 `test_state_03_cash_zero_only_when_complete()`

## tests/sector_panic_rebuild/test_data_guard.py

[打开文件](../../tests/sector_panic_rebuild/test_data_guard.py)

- L20 `test_data_01_stale_snapshot_rejected()`
- L33 `test_data_02_rejects_bad_rows()`
- L45 `test_data_03_future_available_at_excluded()`

## tests/sector_panic_rebuild/test_diagnostic.py

[打开文件](../../tests/sector_panic_rebuild/test_diagnostic.py)

- L19 `test_diag_01_hash_mismatch_blocks()`
- L33 `test_diag_02_missing_event_keeps_denominator()`
- L63 `test_diag_03_future_does_not_change_orders()`
- L74 `test_diag_04_avwap_gap_is_not_repair_level()`
- L97 `test_diag_05_calendar_offsets()`
- L108 `test_diag_06_below_c_fills_above_limit_does_not()`
- L126 `test_diag_07_missing_hold_bar_and_truncation()`
- L169 `test_diag_08_retry_next_session()`
- L185 `test_diag_09_independent_cash_identity()`
- L196 `test_diag_10_tamper_detected(tmp_path=None)`
- L396 `test_diag_11_gaps_document_corporate_actions()`
- L403 `test_diag_12_sample_rule_deterministic()`
- L410 `test_diag_13_checkpoint_restore()`
- L426 `test_diag_14_sample_covers_mixed_and_no_entry()`
- L435 `test_diag_15_refuse_nonempty_and_escape()`
- L445 `test_diag_16_session_not_item()`

## tests/sector_panic_rebuild/test_e2_fill_sample_contract.py

[打开文件](../../tests/sector_panic_rebuild/test_e2_fill_sample_contract.py)

- L34 `_events()`
- L42 `_calendar()`
- L48 `test_contract_forbids_stopping_on_k_fills_and_keeps_economic_unevaluated()`
- L65 `test_validation_events_are_first_four_panel_events_outside_control()`
- L93 `test_each_selected_event_keeps_ten_names_and_has_rule_replay_until()`
- L131 `test_context_next_events_outside_sample_are_listed()`
- L151 `test_resolved_fill_contract_has_six_events_and_parent_inputs()`
- L161 `test_cutoff_does_not_force_flatten_blocked_exit()`
- L182 `test_coverage_insufficient_is_not_an_implementation_fail_flag()`
- L193 `test_independent_wait_reason_does_not_use_engine_labels()`

## tests/sector_panic_rebuild/test_e2_full214.py

[打开文件](../../tests/sector_panic_rebuild/test_e2_full214.py)

- L18 `test_n6_contract_still_loads()`
- L25 `test_full214_preflight_rejects_parent_hash_mismatch()`
- L33 `test_full214_preflight_rejects_denominator_hash_mismatch()`
- L44 `test_stop_on_a_and_sell_on_b_is_not_real_stop_coverage()`
- L89 `test_pending_without_blocked_attempt_is_not_limit_down_coverage()`
- L102 `test_no_repair_missing_natr_is_not_integrity_failure()`
- L125 `test_synthetic_true_is_not_hardcoded_without_pytest_evidence()`
- L134 `test_stop_trigger_after_sell_is_not_real_stop_coverage()`
- L150 `test_block_after_sell_is_not_filled_later()`
- L166 `test_min_adj_low_skips_known_suspend_without_quote()`
- L180 `test_suspend_without_quote_retries_working_sell()`
- L207 `test_limit_down_blocks_then_fills_next_session()`
- L234 `test_max_hold_sells_on_entry_plus_20()`
- L255 `test_wait_window_suspend_without_quote_is_not_missing_price()`
- L277 `test_known_suspend_days_are_not_panic_low_gaps()`

## tests/sector_panic_rebuild/test_e2_full214_audit.py

[打开文件](../../tests/sector_panic_rebuild/test_e2_full214_audit.py)

- L13 `_result(**kwargs)`
- L23 `test_confirmed_no_entry_uses_component_status_not_result_field()`
- L50 `_probe_rows(close_by_date)`
- L59 `test_later_event_does_not_hide_earlier_missing_order()`
- L71 `test_wrong_date_order_does_not_hide_missing_review_order()`
- L84 `test_matching_order_and_same_day_new_event_are_accepted()`
- L102 `test_expired_target_day_order_does_not_hide_same_evening_resubmit()`
- L131 `test_nav_value_and_middle_day_are_not_endpoint_only()`
- L162 `test_baseline_catches_doubled_quantity_and_fee()`

## tests/sector_panic_rebuild/test_e2_risk_inputs.py

[打开文件](../../tests/sector_panic_rebuild/test_e2_risk_inputs.py)

- L30 `_bars(cal, close=101.0, **extra)`
- L43 `test_stop_distance_matches_independent_oracle()`
- L55 `test_fill_price_freezes_matching_stop_level()`
- L66 `test_stop_threshold_just_above_and_below()`
- L75 `test_three_structure_failures_and_single_soft_anchor()`
- L94 `test_exit_priority_stop_over_new_event_and_structure()`
- L113 `test_ratio_stop_uses_fill_not_confirmation_price()`
- L139 `test_fill_day_risk_and_new_event_do_not_erase_trade()`
- L159 `test_suspend_does_not_invent_signal_missing_price_is_not_suspend()`
- L182 `test_checkpoint_keeps_frozen_stop()`
- L204 `test_future_price_does_not_change_past_structure()`
- L233 `test_real_sample_snapshots_are_proven_and_no_repair_skips_hold_risk()`
- L255 `test_stop_mode_conflict_and_confirmation_price_is_not_a_fill()`
- L278 `test_risk_contract_yaml_exists_and_keeps_old_hashes()`

## tests/sector_panic_rebuild/test_e2_workpackages.py

[打开文件](../../tests/sector_panic_rebuild/test_e2_workpackages.py)

- L18 `_bars(cal, close=101.0)`
- L23 `test_wp1_new_event_on_fill_day_keeps_trade()`
- L40 `test_wp2_full_calendar_cutoff_still_fills()`
- L62 `test_wp3_nan_and_false_string_are_not_healthy()`
- L77 `test_wp4_recon_rejects_illegal_fills_and_return_mismatch()`

## tests/sector_panic_rebuild/test_end_to_end.py

[打开文件](../../tests/sector_panic_rebuild/test_end_to_end.py)

- L26 `test_e2e_01_replay_hash_and_oracle()`
- L55 `test_e2e_02_diff_reasons_registered()`
- L78 `test_e2e_03_research_mutations_registered()`
- L89 `test_e2e_04_shadow_mutations_registered()`
- L110 `test_e2e_05_cli_and_not_run_not_pass()`
- L132 `test_all_yaml_ids_have_pytest_markers(pytestconfig)`

## tests/sector_panic_rebuild/test_execution_adapter.py

[打开文件](../../tests/sector_panic_rebuild/test_execution_adapter.py)

- L19 `_order(**kwargs)`
- L32 `test_cash_04_raw_shares_and_lot()`
- L42 `test_cash_05_corporate_actions_explicit()`
- L54 `test_cash_06_caps_include_working_buys()`
- L78 `test_cash_07_passive_breach_not_forced_flat()`
- L90 `test_exec_01_missing_auction_is_unverified()`
- L98 `test_exec_02_partial_equal_limit_suspend()`
- L116 `test_exec_03_duplicate_receipt_idempotent()`
- L127 `test_exec_04_dated_market_rules()`

## tests/sector_panic_rebuild/test_lifecycle_resume.py

[打开文件](../../tests/sector_panic_rebuild/test_lifecycle_resume.py)

- L13 `test_life_01_short_data_not_max_hold()`
- L30 `test_life_02_blocked_exit_keeps_inventory()`
- L49 `test_life_03_checkpoint_matches_full_run()`
- L69 `test_life_04_calendar_vs_data_end()`

## tests/sector_panic_rebuild/test_p1_loss_diagnostic.py

[打开文件](../../tests/sector_panic_rebuild/test_p1_loss_diagnostic.py)

- L42 `_load_script()`
- L50 `_leg(key, side, order_id, submit, target, price, exit_reason=None, limit='101')`
- L69 `_candidate(key, d0, status='REPAIR_CONFIRMED')`
- L81 `_px(value, high=None)`
- L88 `_book()`
- L150 `_run_book()`
- L158 `_row(frame, code)`
- L164 `test_fee_flip_is_not_called_a_price_loss()`
- L174 `test_positive_net_close_then_loss_and_intraday_high_is_ignored()`
- L192 `test_suspension_carry_is_not_a_new_observation_or_a_fill_in()`
- L209 `test_unexplained_gap_is_not_interpolated_and_blocks_the_path_label()`
- L221 `test_zero_session_hold_is_separate_and_confirmation_is_not_backfilled()`
- L261 `test_pre_submit_fields_are_not_execution_outcomes()`
- L273 `test_dependence_groups_are_deterministic_and_cover_filled_events()`
- L299 `test_concentration_does_not_divide_by_the_small_net_pnl()`
- L339 `test_accounting_matches_attribution_and_rejects_bad_pairs()`
- L391 `test_json_rejects_nan_and_script_refuses_existing_output(tmp_path=None)`
- L415 `test_cross_tab_keeps_fee_flip_and_giveback_on_separate_axes()`
- L432 `_one_trade(key, buy_submit, buy_day, sell_submit, sell_day, buy_px, sell_px, d0, prices, reason='STOP')`
- L440 `test_early_exit_leaves_later_horizons_empty()`
- L462 `test_suspension_carry_and_unexplained_gap_stay_distinct()`
- L485 `test_same_stock_different_events_do_not_cross_orders_or_paths()`
- L524 `test_cross_year_cross_sector_overlap_keeps_attribution()`
- L566 `test_near_zero_net_is_not_the_concentration_denominator()`
- L602 `test_prices_after_submit_do_not_change_pre_submit_fields()`
- L634 `test_duplicate_keys_quantity_mismatch_and_hash_change_fail_closed()`
- L670 `test_confirmation_after_submit_stops_before_a_ledger()`
- L686 `test_incomplete_path_with_a_positive_close_is_not_giveback()`
- L710 `test_same_event_winner_and_loser_are_netted_without_replacing_trade_totals()`
- L742 `test_changed_input_stops_the_entry_without_a_success_report()`

## tests/sector_panic_rebuild/test_portfolio_p1_book.py

[打开文件](../../tests/sector_panic_rebuild/test_portfolio_p1_book.py)

- L25 `_book(total: str)`
- L29 `_app(signal, sector, event, code, *, ok=True, reason='SUBMIT_NEXT_CLOSE', limit='10', nxt=None)`
- L42 `_px(price: str)`
- L46 `_state(book: PortfolioBook, code: str='000001.SZ')`
- L58 `test_cash_competition_sorts_applications_known_on_the_submit_night()`
- L79 `test_expiry_releases_full_reserve_and_a_later_application_can_be_submitted()`
- L121 `test_lower_fill_price_keeps_quantity_and_releases_unused_reserve()`
- L144 `test_suspended_sell_keeps_the_slot_and_does_not_duplicate_the_order()`
- L181 `test_same_name_check_runs_only_after_the_strategy_flag()`
- L213 `test_sale_proceeds_post_after_match_and_use_the_frozen_exit_fee()`
- L255 `test_missing_bar_is_not_a_suspension_for_buy_or_sell()`
- L295 `test_filled_buy_keeps_next_event_and_later_arrival_submits_one_sell()`
- L319 `test_same_day_next_event_fill_and_nofill_follow_arrival_before_match()`
- L367 `test_match_conflict_and_invalid_price_leave_the_book_unchanged()`
- L405 `test_name_slot_rejects_the_21st_name_while_cash_remains()`

## tests/sector_panic_rebuild/test_portfolio_p1_driver.py

[打开文件](../../tests/sector_panic_rebuild/test_portfolio_p1_driver.py)

- L13 `_weekdays(start: int, count: int)`
- L23 `_candidate(code, signal, event, **overrides)`
- L42 `_bars(spec: dict[int, dict[str, str]])`
- L54 `test_prices_drive_entry_fill_structure_exit_and_daily_nav()`
- L95 `test_cash_shortage_reapplies_from_the_next_review_close()`
- L136 `test_same_day_next_event_fill_sells_and_miss_does_not()`
- L175 `test_same_day_new_event_is_the_only_exit_when_structure_and_stop_are_quiet()`
- L202 `test_missing_bar_rolls_back_the_day_and_stops_later_nav()`
- L252 `test_last_session_keeps_an_unscheduled_exit_obligation()`
- L276 `test_suspension_reuses_last_mark_and_a_later_gap_fails()`
- L300 `test_second_event_fill_replaces_the_previous_risk_state()`
- L332 `test_flat_candidate_is_abandoned_and_a_completed_candidate_cannot_reenter()`
- L368 `test_limit_prints_block_only_the_matching_order_side_and_still_mark()`
- L436 `test_candidate_records_roll_back_when_the_session_fails_after_them()`
- L469 `test_limit_up_close_is_the_mark_used_after_a_later_suspension()`
- L487 `test_flat_candidate_inside_the_entry_window_stays_incomplete()`
- L502 `test_cutoff_on_the_last_review_day_does_not_finish_a_qualified_candidate()`
- L550 `test_later_new_event_does_not_rewrite_no_repair_or_window_exhaustion()`
- L569 `test_independent_rebuild_rejects_cash_bump_and_deleted_day()`
- L595 `test_published_nav_uses_sorted_marks_not_insertion_order()`
- L615 `test_comparator_keeps_window_terminal_and_checks_sell_limit_and_quantity()`

## tests/sector_panic_rebuild/test_portfolio_p1_full214_audit.py

[打开文件](../../tests/sector_panic_rebuild/test_portfolio_p1_full214_audit.py)

- L19 `_weekdays(start: int, count: int)`
- L29 `_candidate(code, signal, event, **overrides)`
- L48 `_tradable(spec: dict[int, dict[str, str]])`
- L62 `_audit(result, bars, initial=Decimal('1'))`
- L70 `test_suspension_carries_the_later_limit_close()`
- L88 `test_driver_suspension_mark_matches_frozen_carry_and_rejects_a_stale_price()`
- L116 `test_cash_and_slot_labels_require_the_rebuilt_account()`
- L146 `test_same_session_sell_proceeds_follow_book_match_order()`
- L175 `test_twenty_first_name_is_a_supported_slot_reject()`

## tests/sector_panic_rebuild/test_rebuild_review_regressions.py

[打开文件](../../tests/sector_panic_rebuild/test_rebuild_review_regressions.py)

- L24 `test_checkpoint_does_not_sell_before_entry()`
- L46 `test_mtm_ignores_future_last_bar()`
- L57 `test_nan_review_does_not_submit()`
- L72 `test_missing_wait_window_is_not_cash_zero()`
- L87 `test_blocked_exit_retries_after_limit_down()`
- L102 `test_structure_break_and_new_event_exit()`
- L114 `test_gates_reject_open_unknown_and_inf()`
- L136 `test_handfilled_passed_is_not_acceptance()`
- L191 `test_missing_stop_bar_is_integrity_failure()`
- L210 `test_retry_sells_submit_before_target()`
- L225 `test_mutation_parser_requires_assertion_error()`
- L250 `test_valid_evidence_report_can_pass_one_row()`
- L288 `test_one_nodeid_cannot_cover_all_acceptance_ids()`
- L331 `test_structured_report_rejects_one_node_for_all_ids()`
- L376 `_full_passing_evidence(*, exitstatus=0, fail_unmarked=None, drop_catalog=False)`
- L420 `test_session_fail_unmarked_regression_keeps_item_pass()`
- L453 `test_executed_entry_cannot_bypass_session()`
- L490 `test_run_id_rejects_path_escape()`

## tests/sector_panic_rebuild/test_statistics_and_dependence.py

[打开文件](../../tests/sector_panic_rebuild/test_statistics_and_dependence.py)

- L13 `_frame(rows)`
- L20 `_ok_rows()`
- L31 `test_stat_01_missing_or_nan_blocks_all_economic()`
- L49 `test_stat_02_artificial_plus_failure_cannot_pass()`
- L63 `test_stat_03_counts_are_split()`
- L80 `test_stat_04_overlap_merges_and_does_not_affect_orders()`
- L98 `test_stat_05_purge_and_train_only_standardize()`
- L122 `test_stat_06_three_return_definitions()`

## tests/test_adj_factor_cache_strict.py

[打开文件](../../tests/test_adj_factor_cache_strict.py)

- L10 `class TestAdjFactorStrictMode`
- L13 `TestAdjFactorStrictMode.test_partial_cache_returns_empty_with_diag_attrs(self)`
- L46 `TestAdjFactorStrictMode.test_allow_partial_true_returns_partial(self)`
- L74 `TestAdjFactorStrictMode.test_cache_hit_full_coverage_returns_all(self)`
- L109 `TestAdjFactorStrictMode.test_dedup_before_write(self)`
- L135 `TestAdjFactorStrictMode.test_per_day_stock_coverage_check(self)`
- L173 `TestAdjFactorStrictMode.test_zero_row_trade_day_counts_as_low_coverage(self)`
- L210 `TestAdjFactorStrictMode.test_large_batch_partial_failure_does_not_write_partial_cache(self)`
- L238 `TestAdjFactorStrictMode.test_date_range_list_fetches_by_trade_date(self)`

## tests/test_alpha_factors_v4.py

[打开文件](../../tests/test_alpha_factors_v4.py)

- L51 `sample_prices()`
- L74 `sample_financial_data()`
- L106 `sample_industry_map()`
- L118 `class TestPITAlignment`
- L121 `TestPITAlignment.test_available_date_uses_ann_date(self)`
- L128 `TestPITAlignment.test_fallback_when_ann_date_none(self)`
- L134 `TestPITAlignment.test_fallback_when_ann_date_nan(self)`
- L139 `TestPITAlignment.test_quarterly_fallback(self)`
- L144 `TestPITAlignment.test_detect_report_type_annual(self)`
- L147 `TestPITAlignment.test_detect_report_type_semi_annual(self)`
- L150 `TestPITAlignment.test_detect_report_type_quarterly(self)`
- L154 `TestPITAlignment.test_growth_ttm_has_available_date(self, sample_financial_data)`
- L163 `TestPITAlignment.test_stability_8q_has_available_date(self, sample_financial_data)`
- L176 `class TestTechnicalFactors`
- L179 `TestTechnicalFactors.test_skip_momentum_shape(self, sample_prices)`
- L187 `TestTechnicalFactors.test_skip_momentum_values_finite(self, sample_prices)`
- L193 `TestTechnicalFactors.test_risk_adjusted_momentum(self, sample_prices)`
- L199 `TestTechnicalFactors.test_volume_confirmed_momentum(self, sample_prices)`
- L205 `TestTechnicalFactors.test_trend_quality(self, sample_prices)`
- L211 `TestTechnicalFactors.test_liquidity_adjusted_reversal(self, sample_prices)`
- L218 `TestTechnicalFactors.test_vol_adjusted_reversal(self, sample_prices)`
- L225 `TestTechnicalFactors.test_low_beta(self, sample_prices)`
- L232 `TestTechnicalFactors.test_drawdown_resilience(self, sample_prices)`
- L239 `TestTechnicalFactors.test_low_beta_stable_monthly_has_fewer_dates(self, sample_prices)`
- L247 `TestTechnicalFactors.test_reversal_low_turnover_weekly_has_fewer_dates(self, sample_prices)`
- L257 `TestTechnicalFactors.test_empty_prices_returns_empty(self)`
- L264 `class TestFundamentalFactors`
- L267 `TestFundamentalFactors.test_growth_ttm(self, sample_financial_data)`
- L276 `TestFundamentalFactors.test_stability_8q(self, sample_financial_data)`
- L285 `TestFundamentalFactors.test_earnings_acceleration(self, sample_financial_data)`
- L293 `TestFundamentalFactors.test_profitability_quality(self, sample_financial_data)`
- L304 `TestFundamentalFactors.test_ocf_to_profit(self, sample_financial_data)`
- L310 `TestFundamentalFactors.test_fundamental_ttm(self, sample_financial_data)`
- L319 `TestFundamentalFactors.test_empty_financial_data_returns_empty(self)`
- L329 `TestFundamentalFactors.test_missing_field_returns_empty(self, sample_financial_data)`
- L336 `class TestIndustryRelative`
- L339 `TestIndustryRelative.test_industry_relative(self, sample_prices, sample_industry_map)`
- L348 `TestIndustryRelative.test_industry_relative_empty_base(self, sample_industry_map)`
- L354 `TestIndustryRelative.test_industry_relative_empty_map(self, sample_prices)`
- L362 `class TestCSProcessing`
- L365 `TestCSProcessing.test_cs_processing_produces_finite_values(self, sample_prices)`
- L373 `TestCSProcessing.test_cs_empty_input(self)`
- L380 `class TestPITDedup`
- L383 `TestPITDedup.test_dedup_keeps_most_recent_available_date(self, sample_financial_data, sample_prices)`
- L416 `TestPITDedup.test_dedup_preserves_pit_constraint(self, sample_financial_data, sample_prices)`
- L439 `TestPITDedup.test_growth_factors_output_unique_keys(self, sample_financial_data)`
- L466 `TestPITDedup.test_multi_report_period_same_trade_date(self, sample_financial_data, sample_prices)`
- L498 `TestPITDedup.test_duplicate_assertion_would_fire(self)`
- L514 `class TestFactorConfig`
- L517 `TestFactorConfig.test_universe_config_loads(self)`
- L531 `TestFactorConfig.test_build_config_loads(self)`
- L542 `TestFactorConfig.test_all_factors_have_sign_hint(self)`
- L552 `TestFactorConfig.test_p0_factors_cover_all_categories(self)`

## tests/test_alpha_inputs_v4.py

[打开文件](../../tests/test_alpha_inputs_v4.py)

- L33 `class TestFutureLeakage`
- L36 `TestFutureLeakage.test_no_leakage_clean_data(self)`
- L51 `TestFutureLeakage.test_future_leakage_detected(self)`
- L64 `TestFutureLeakage.test_single_leakage_record_fails(self)`
- L77 `class TestStaleData`
- L80 `TestStaleData.test_fresh_data_passes(self)`
- L92 `TestStaleData.test_stale_data_warns(self)`
- L112 `TestStaleData.test_technical_factor_tighter_lag(self)`
- L126 `class TestDuplicateDetection`
- L129 `TestDuplicateDetection.test_clean_data_no_dupes(self)`
- L139 `TestDuplicateDetection.test_duplicates_detected(self)`
- L149 `TestDuplicateDetection.test_high_duplicate_rate_fails(self)`
- L168 `class TestConstantValueDetection`
- L171 `TestConstantValueDetection.test_variable_factor_passes(self)`
- L181 `TestConstantValueDetection.test_constant_factor_detected(self)`
- L192 `class TestCoverageCheck`
- L195 `TestCoverageCheck.test_adequate_coverage(self)`
- L209 `TestCoverageCheck.test_low_coverage_detected(self)`
- L224 `class TestMissingAvailableDate`
- L227 `TestMissingAvailableDate.test_missing_field_detected(self)`
- L239 `TestMissingAvailableDate.test_null_available_date(self)`
- L251 `class TestEmptyCache`
- L254 `TestEmptyCache.test_empty_cache_fails(self)`
- L262 `class TestBlockedFactors`
- L265 `TestBlockedFactors.test_factor_blocked_by_missing_source(self)`
- L284 `TestBlockedFactors.test_factor_not_blocked_when_data_available(self)`
- L302 `TestBlockedFactors.test_factor_blocked_by_missing_fields(self)`
- L322 `class TestMaxLagDays`
- L325 `TestMaxLagDays.test_max_lag_values(self)`
- L330 `TestMaxLagDays.test_min_coverage_value(self)`

## tests/test_audit_cache_adj_factor.py

[打开文件](../../tests/test_audit_cache_adj_factor.py)

- L14 `class TestAdjFactorDedupAudit`
- L17 `TestAdjFactorDedupAudit._make_mock_args(self, start='20170101', end='20241231', verbose=False)`
- L25 `TestAdjFactorDedupAudit._make_mock_loader(self, adjf_df=None)`
- L48 `TestAdjFactorDedupAudit._make_mock_calendar(self, n_trade_days=100)`
- L57 `TestAdjFactorDedupAudit.test_adj_factor_dedup_pass_when_no_duplicates(self, mock_get_loader, mock_get_calendar)`
- L72 `TestAdjFactorDedupAudit.test_adj_factor_dedup_fail_when_duplicates(self, mock_get_loader, mock_get_calendar)`
- L92 `TestAdjFactorDedupAudit.test_adj_factor_dedup_verbose_shows_keys(self, mock_get_loader, mock_get_calendar)`
- L113 `TestAdjFactorDedupAudit.test_adj_factor_coverage_pass(self, mock_get_loader, mock_get_calendar)`
- L128 `TestAdjFactorDedupAudit.test_empty_adj_factor_fails_coverage(self, mock_get_loader, mock_get_calendar)`

## tests/test_audit_cache_factor_duplicates.py

[打开文件](../../tests/test_audit_cache_factor_duplicates.py)

- L21 `class TestAuditDuplicateDetection`
- L24 `TestAuditDuplicateDetection.test_detect_simple_duplicates(self)`
- L34 `TestAuditDuplicateDetection.test_no_duplicates_returns_zero(self)`
- L44 `TestAuditDuplicateDetection.test_identical_rows_counted_as_duplicates(self)`
- L55 `TestAuditDuplicateDetection.test_different_values_same_key_counted(self)`
- L66 `TestAuditDuplicateDetection.test_dedup_keep_last_retains_one_row(self)`
- L88 `class TestAuditThresholdEnforcement`
- L91 `TestAuditThresholdEnforcement.test_high_duplicate_rate_flags_fail(self)`
- L102 `TestAuditThresholdEnforcement.test_low_duplicate_rate_does_not_flag(self)`
- L112 `TestAuditThresholdEnforcement.test_zero_duplicates_is_clean(self)`
- L121 `TestAuditThresholdEnforcement.test_growth_factor_duplicate_rates_are_extreme(self)`
- L135 `class TestBuildScriptAssertion`
- L138 `TestBuildScriptAssertion.test_assertion_fires_on_duplicates(self)`
- L151 `TestBuildScriptAssertion.test_assertion_passes_on_clean_data(self)`
- L162 `TestBuildScriptAssertion.test_audit_cache_factor_coverage_simulation(self)`

## tests/test_audit_cache_limit_status.py

[打开文件](../../tests/test_audit_cache_limit_status.py)

- L21 `class TestAuditLimitStatus`
- L24 `TestAuditLimitStatus.test_audit_includes_trade_day_coverage(self)`
- L48 `TestAuditLimitStatus.test_limit_status_mode_default_is_exec(self)`
- L56 `TestAuditLimitStatus.test_limit_status_mode_full_calendar_accepted(self)`
- L64 `TestAuditLimitStatus.test_exec_mode_detail_mentions_exec_scoped(self)`
- L73 `TestAuditLimitStatus.test_full_calendar_mode_fails_low_trade_day_coverage(self)`

## tests/test_backtester_dependency_loading.py

[打开文件](../../tests/test_backtester_dependency_loading.py)

- L16 `test_build_backtester_loads_universe_and_tradable()`
- L28 `test_backtest_phases_use_loaded_backtester_helper()`

## tests/test_backtester_end_boundary.py

[打开文件](../../tests/test_backtester_end_boundary.py)

- L4 `test_simulate_caps_period_end_at_backtest_end(monkeypatch)`

## tests/test_benchmark_metrics_status.py

[打开文件](../../tests/test_benchmark_metrics_status.py)

- L10 `class TestBenchmarkMetricsStatus`
- L13 `TestBenchmarkMetricsStatus.setup_method(self)`
- L16 `TestBenchmarkMetricsStatus.test_empty_benchmark_returns_missing_status(self)`
- L28 `TestBenchmarkMetricsStatus.test_insufficient_benchmark_periods(self)`
- L42 `TestBenchmarkMetricsStatus.test_benchmark_annualized_return_none_when_not_ok(self)`
- L71 `TestBenchmarkMetricsStatus.test_report_shows_na_not_zero(self)`
- L118 `TestBenchmarkMetricsStatus.test_ytd_unstable_flagged_in_report(self)`

## tests/test_benchmark_optimizer_pipeline.py

[打开文件](../../tests/test_benchmark_optimizer_pipeline.py)

- L15 `class TestBenchmarkAlignment`
- L18 `TestBenchmarkAlignment.test_benchmark_excludes_exec_date(self)`
- L36 `class TestPriceAdjustmentPipeline`
- L39 `TestPriceAdjustmentPipeline.test_adj_prices_computation(self)`
- L61 `TestPriceAdjustmentPipeline.test_raw_prices_unchanged(self)`
- L82 `class TestPanelLoaderBatching`
- L85 `TestPanelLoaderBatching.test_write_data_creates_partitions(self, tmp_path)`
- L98 `TestPanelLoaderBatching.test_query_handles_many_stocks(self, tmp_path)`
- L120 `class TestRobustnessCosts`
- L123 `TestRobustnessCosts.test_cost_multiplier_changes_costs(self)`
- L139 `TestRobustnessCosts.test_cost_multiplier_applied_to_portfolio_level(self)`
- L158 `TestRobustnessCosts.test_backtester_cost_scenarios_change_net_metrics_without_leakage(self, monkeypatch)`
- L249 `class TestWeightMaxOptimization`
- L252 `TestWeightMaxOptimization.test_weight_max_changes_constraint(self)`
- L264 `TestWeightMaxOptimization.test_infeasible_config_detected(self)`
- L271 `TestWeightMaxOptimization.test_feasible_config_passes(self)`
- L278 `TestWeightMaxOptimization.test_backtester_feasibility_check(self)`
- L302 `TestWeightMaxOptimization.test_weight_max_0_10_is_feasible(self)`
- L327 `class TestWeightMaxOptimizedPath`
- L330 `TestWeightMaxOptimizedPath.test_weight_max_002_vs_005_feasibility_differs(self)`
- L384 `TestWeightMaxOptimizedPath.test_weight_max_001_infeasible_with_50_stocks(self)`
- L417 `TestWeightMaxOptimizedPath.test_constraint_builder_uses_weight_max(self)`
- L437 `class TestBiweeklyNotCalled`
- L440 `TestBiweeklyNotCalled.test_rebalance_frequency_default_excludes_biweekly(self)`
- L459 `TestBiweeklyNotCalled.test_explicit_frequencies_respected(self)`
- L477 `class TestBufferSelection`
- L480 `TestBufferSelection.test_retained_stock_with_rank_60_exit_80_is_kept(self)`
- L508 `TestBufferSelection.test_new_stock_beyond_entry_rank_not_selected(self)`
- L541 `TestBufferSelection.test_buffer_reduces_turnover_vs_no_buffer(self)`

## tests/test_cache_coverage.py

[打开文件](../../tests/test_cache_coverage.py)

- L13 `_authoritative_calendar(start: str, end: str)`
- L25 `class TestCacheCoverage`
- L28 `TestCacheCoverage.test_covers_range_positive(self, tmp_path)`
- L47 `TestCacheCoverage.test_covers_range_negative_range_not_covered(self, tmp_path)`
- L66 `TestCacheCoverage.test_covers_range_empty_table(self, tmp_path)`
- L72 `TestCacheCoverage.test_canonical_file_wins_over_legacy_for_all_helpers(self, tmp_path)`
- L96 `TestCacheCoverage.test_cache_checker_ignores_superseded_legacy_file(self, tmp_path, monkeypatch)`
- L113 `TestCacheCoverage.test_calendar_load_rejects_wrong_date_range(self)`
- L148 `TestCacheCoverage.test_calendar_load_keeps_valid_range(self)`
- L165 `TestCacheCoverage.test_cache_rejects_wrong_year_parquet(self, tmp_path)`
- L191 `class TestFetchManifest`
- L194 `TestFetchManifest.test_records_requested_codes_not_only_returned_codes(self, tmp_path)`
- L206 `TestFetchManifest.test_adjacent_year_queries_cover_combined_range(self, tmp_path)`
- L217 `TestFetchManifest.test_different_code_query_does_not_prove_coverage(self, tmp_path)`
- L228 `TestFetchManifest.test_two_preconstructed_instances_merge_without_lost_update(self, tmp_path)`
- L244 `TestFetchManifest.test_dead_owner_lock_is_reclaimed(self, tmp_path, monkeypatch)`
- L253 `TestFetchManifest.test_active_owner_lock_is_not_deleted(self, tmp_path)`
- L263 `TestFetchManifest.test_malformed_lock_fails_closed(self, tmp_path)`
- L273 `class TestTushareCoverageContracts`
- L275 `TestTushareCoverageContracts._client(tmp_path)`
- L282 `TestTushareCoverageContracts.test_suspend_uses_official_range_parameters_and_records_empty(self, tmp_path)`
- L310 `TestTushareCoverageContracts.test_daily_by_trade_date_rejects_partial_fresh_market_day(self, tmp_path)`
- L327 `TestTushareCoverageContracts.test_daily_by_trade_date_accepts_complete_fresh_market_day(self, tmp_path)`
- L341 `TestTushareCoverageContracts.test_daily_by_trade_date_rejects_inexact_cached_code_set(self, tmp_path)`
- L372 `TestTushareCoverageContracts.test_daily_basic_list_is_queried_one_code_at_a_time(self, tmp_path)`
- L406 `TestTushareCoverageContracts.test_daily_basic_partial_failure_is_not_manifest_complete(self, tmp_path)`
- L432 `TestTushareCoverageContracts.test_legacy_daily_basic_claim_cannot_hide_hollow_cache(self, tmp_path)`
- L479 `TestTushareCoverageContracts.test_stk_limit_list_is_queried_one_code_at_a_time(self, tmp_path)`
- L514 `TestTushareCoverageContracts.test_suspend_loader_normalizes_suspend_date(self, tmp_path, monkeypatch)`

## tests/test_calendar_cache.py

[打开文件](../../tests/test_calendar_cache.py)

- L14 `class TestCalendarSingletonPollution`
- L17 `TestCalendarSingletonPollution.test_narrow_load_does_not_shrink_wide_calendar(self, monkeypatch)`
- L50 `TestCalendarSingletonPollution.test_weekly_dates_after_narrow_load_attempt(self, monkeypatch)`
- L83 `TestCalendarSingletonPollution.test_load_fully_covered_returns_immediately(self)`

## tests/test_candidate_v4_r2_gate_enforcement.py

[打开文件](../../tests/test_candidate_v4_r2_gate_enforcement.py)

- L26 `class TestGateEnforcement`
- L30 `TestGateEnforcement.cfg(self)`
- L35 `TestGateEnforcement.test_at_least_one_alpha_pass_or_documented_blocking(self, cfg)`
- L74 `TestGateEnforcement.test_no_fail_in_enabled(self, cfg)`
- L89 `TestGateEnforcement.test_no_data_missing_in_enabled(self, cfg)`
- L103 `TestGateEnforcement.test_watch_neutral_only_not_in_alpha_enabled(self, cfg)`
- L121 `TestGateEnforcement.test_disabled_factors_comprehensive(self, cfg)`
- L144 `TestGateEnforcement.test_pending_gate_factors_have_clear_status(self, cfg)`
- L161 `class TestRegimeAllocatorGateEnforcement`
- L165 `TestRegimeAllocatorGateEnforcement.regime_cfg(self)`
- L171 `TestRegimeAllocatorGateEnforcement.test_empty_sleeves_have_zero_weight(self, regime_cfg)`
- L187 `TestRegimeAllocatorGateEnforcement.test_weights_sum_to_one_or_zero(self, regime_cfg)`
- L206 `TestRegimeAllocatorGateEnforcement.test_non_empty_sleeves_have_positive_total_weight(self, regime_cfg)`
- L222 `TestRegimeAllocatorGateEnforcement.test_only_defensive_non_empty_no_formal_alpha_claim(self, regime_cfg)`

## tests/test_component_avwap_loss_audit.py

[打开文件](../../tests/test_component_avwap_loss_audit.py)

- L16 `_path(closes, daily_vwaps=None)`
- L28 `_analyze(closes, daily_vwaps=None, sale_position=1)`
- L40 `test_post_exit_avwap_reclaim_then_failure_is_state_based()`
- L50 `test_post_exit_avwap_reclaim_held_to_boundary_and_entry_recovery()`
- L58 `test_post_exit_no_avwap_reclaim_before_causal_boundary()`
- L65 `test_actual_sale_at_boundary_has_no_post_exit_outcome_label()`
- L72 `test_suspension_does_not_change_avwap_numerator_or_create_transition()`
- L93 `test_suspension_ignores_a_retained_raw_price_row()`
- L109 `test_event_boundary_uses_next_same_sector_entry_only_when_earlier()`
- L123 `test_exit_group_separates_stop_arm_state_and_scheduled_boundaries()`

## tests/test_component_entry_avwap_gate.py

[打开文件](../../tests/test_component_entry_avwap_gate.py)

- L17 `_calendar(count=28)`
- L24 `_panel(codes, calendar, t1_closes=None)`
- L42 `_selection(codes)`
- L53 `test_signal_avwap_gate_is_volume_weighted_and_strictly_above()`
- L65 `test_t1_suspension_is_blocked_cash_not_data_failure()`
- L78 `test_gated_event_attempts_t2_and_does_not_renormalize_passed_budgets()`
- L99 `test_no_gate_pass_is_an_eligible_all_cash_event()`
- L116 `test_gated_wrapper_can_run_frozen_r6_without_changing_component_budgets()`

## tests/test_component_natr_stop.py

[打开文件](../../tests/test_component_natr_stop.py)

- L23 `_calendar(count=35)`
- L30 `_panel(calendar, closes=None)`
- L46 `_selection()`
- L52 `_confirmation(calendar)`
- L62 `test_confirmation_natr_uses_valid_sessions_and_captures_reopen_gap()`
- L80 `test_confirmation_natr_is_unchanged_by_future_prices()`
- L90 `test_confirmation_natr_fails_on_unexplained_gap_in_required_window()`
- L99 `test_cost_adjusted_risk_weight_respects_equal_cap_and_risk_slot()`
- L108 `test_adaptive_event_keeps_unused_weight_in_cash_and_exits_next_close()`
- L135 `test_risk_violation_is_not_a_data_failure_and_only_blocks_deployment()`
- L159 `test_cap20_shadow_excludes_without_redistribution()`
- L179 `test_risk_overrun_uses_component_stop_fields_without_merge_suffixes()`
- L215 `test_cap20_attribution_uses_explicit_arm_column_names()`

## tests/test_component_repair_confirmation.py

[打开文件](../../tests/test_component_repair_confirmation.py)

- L15 `_calendar(count=35)`
- L22 `_selection(codes)`
- L33 `_panel(paths, calendar)`
- L51 `_set_ohlc(panel, code, calendar, values)`
- L59 `_legal_path(panel, code, calendar, shift=0)`
- L74 `test_t1_avwap_reclaim_then_new_low_never_confirms()`
- L93 `test_break_without_hold_returns_to_observation_and_does_not_enter()`
- L107 `test_structural_repair_confirms_at_t5_and_enters_at_t6()`
- L124 `test_future_prices_do_not_change_existing_confirmation()`
- L144 `test_staggered_component_entries_use_each_repair_clock()`
- L168 `test_missing_required_repair_input_fails_closed()`

## tests/test_component_repair_quality.py

[打开文件](../../tests/test_component_repair_quality.py)

- L15 `_calendar(count=35)`
- L22 `_selection(codes)`
- L31 `_panel(codes, calendar)`
- L53 `_set_ohlc(panel, code, calendar, values)`
- L61 `_legal_path(panel, code, calendar, shift=0)`
- L74 `test_q1_requires_three_complete_sessions_after_break()`
- L95 `test_q1_hold_failure_resets_count_and_does_not_confirm_early()`
- L112 `test_intraday_repair_level_touch_is_allowed_when_higher_low_holds()`
- L125 `test_higher_low_intraday_break_invalidates_current_hold()`
- L140 `test_suspension_does_not_advance_q1_hold_count()`
- L157 `test_q2_waits_for_dynamic_breadth_and_then_batches_entries()`
- L182 `test_q2_threshold_uses_ceiling_of_fixed_initial_count()`
- L199 `test_q2_breadth_is_not_latched_after_validity_loss()`
- L218 `test_future_prices_do_not_change_existing_q1_or_q2_entry()`
- L245 `test_missing_required_input_fails_closed()`
- L259 `test_boundary_blocks_confirmation_without_next_entry_session()`
- L273 `test_final_runtime_date_confirmation_is_right_censored_without_entry_session()`
- L293 `test_empty_scan_window_returns_stable_empty_state_and_breadth_ledgers()`
- L309 `test_q1_and_q2_ledgers_do_not_reuse_bare_e2_status_column()`

## tests/test_component_repair_quality_audit.py

[打开文件](../../tests/test_component_repair_quality_audit.py)

- L13 `_calendar()`
- L20 `_panel(calendar)`
- L33 `test_postpath_fast_recovery_remains_a_stop_subgroup()`
- L59 `test_funnel_keeps_structural_missingness_as_status_not_zero()`
- L89 `test_feature_statistics_use_episode_blocks_and_never_promote_features()`

## tests/test_cost_aware_objective.py

[打开文件](../../tests/test_cost_aware_objective.py)

- L13 `class TestCostAwareParameters`
- L16 `TestCostAwareParameters.test_cost_aware_lambda_defaults(self)`
- L29 `TestCostAwareParameters.test_turnover_penalty_separate_from_cost_aware(self)`
- L43 `class TestCostObjectiveNotDestroyingReturns`
- L46 `TestCostObjectiveNotDestroyingReturns.test_cost_penalty_magnitude_reasonable(self)`
- L63 `class TestGridComparison`
- L66 `TestGridComparison.test_parameter_grids_are_distinct(self)`
- L85 `TestGridComparison.test_no_double_penalty(self)`
- L100 `class TestCostModelIntegration`
- L103 `TestCostModelIntegration.test_linear_cost_approximation(self)`
- L127 `class TestCostAwareParamsReachSolver`
- L130 `TestCostAwareParamsReachSolver.test_cost_aware_params_reach_solve_with_retries(self)`
- L165 `TestCostAwareParamsReachSolver.test_relax_constraints_tiered_accepts_cost_params(self)`
- L180 `TestCostAwareParamsReachSolver.test_cost_aware_diag_records_params(self)`
- L190 `class TestConstraintRelaxationBranching`
- L193 `TestConstraintRelaxationBranching.test_none_calls_solve_not_relax(self)`
- L206 `TestConstraintRelaxationBranching.test_tiered_calls_relax_not_solve_only(self)`

## tests/test_data_missing_factor_fix.py

[打开文件](../../tests/test_data_missing_factor_fix.py)

- L27 `build_module()`
- L43 `class TestSourceMissingReturnsDiagnosis`
- L46 `TestSourceMissingReturnsDiagnosis.test_missing_cashflow_source_diagnosed(self, build_module)`
- L51 `TestSourceMissingReturnsDiagnosis.test_missing_balancesheet_source_diagnosed(self, build_module)`
- L56 `TestSourceMissingReturnsDiagnosis.test_field_missing_returns_field_missing(self, build_module)`
- L72 `TestSourceMissingReturnsDiagnosis.test_source_missing_returns_source_missing(self, build_module)`
- L91 `class TestPITAlignment`
- L94 `TestPITAlignment.test_available_date_not_in_future(self, build_module)`
- L117 `TestPITAlignment.test_ann_date_preferred_over_end_date(self, build_module)`
- L124 `TestPITAlignment.test_fallback_when_ann_date_missing(self, build_module)`
- L133 `TestPITAlignment.test_momentum_skip_window(self, build_module)`
- L150 `class TestUniqueKeys`
- L153 `TestUniqueKeys.test_ocf_to_profit_no_duplicate_keys(self, build_module)`
- L167 `TestUniqueKeys.test_stability_8q_no_duplicate_keys(self, build_module)`
- L189 `class TestDailyBasicLoading`
- L192 `TestDailyBasicLoading.test_daily_basic_loads_from_parquet(self, build_module, tmp_path, monkeypatch)`
- L213 `TestDailyBasicLoading.test_daily_data_has_required_fields(self, build_module)`
- L228 `class TestIndustryRank`
- L231 `TestIndustryRank.test_industry_rank_groups_correctly(self, build_module)`
- L252 `TestIndustryRank.test_industry_static_fallback_loaded(self, build_module)`
- L259 `TestIndustryRank.test_industry_relative_respects_min_stocks(self)`
- L270 `class TestAuditOutput`
- L273 `TestAuditOutput.test_audit_script_produces_csv(self, tmp_path, monkeypatch)`
- L297 `TestAuditOutput.test_no_factor_shows_empty_cache(self)`
- L308 `TestAuditOutput.test_diagnosis_csv_in_run_dir(self)`
- L319 `class TestFactorFormulaCorrectness`
- L322 `TestFactorFormulaCorrectness.test_valuation_reversion_negative_for_high_percentile(self, build_module)`
- L335 `TestFactorFormulaCorrectness.test_ocf_to_profit_positive_ratio(self, build_module)`

## tests/test_data_pipeline.py

[打开文件](../../tests/test_data_pipeline.py)

- L21 `class TestTradingCalendar`
- L24 `TestTradingCalendar.test_int_to_datetime(self)`
- L34 `TestTradingCalendar.test_date_range_generation(self)`
- L39 `TestTradingCalendar.test_next_trade_day_no_data(self)`
- L54 `class TestPriceAdjuster`
- L57 `TestPriceAdjuster.test_compute_adj_prices(self)`
- L86 `TestPriceAdjuster.test_compute_forward_returns(self)`
- L104 `class TestUniverseBuilder`
- L108 `TestUniverseBuilder.mock_universe(self)`
- L130 `TestUniverseBuilder.test_forward_fill_constituents(self, mock_universe)`
- L141 `TestUniverseBuilder.test_no_future_constituents(self, mock_universe)`
- L147 `TestUniverseBuilder.test_ipo_filter(self, mock_universe)`
- L157 `TestUniverseBuilder.test_delist_filter(self, mock_universe)`
- L170 `class TestTradableMask`
- L173 `TestTradableMask.test_mask_init(self)`
- L178 `TestTradableMask.test_basic_mask(self)`
- L195 `TestTradableMask.test_suspend_mask(self)`
- L216 `TestTradableMask.test_suspend_mask_daily_trade_date_flags(self)`
- L237 `TestTradableMask.test_missing_limit_row_does_not_mark_sibling_checked(self)`
- L262 `TestTradableMask.test_nan_limits_are_unknown_not_tradable(self)`
- L283 `TestTradableMask.test_mask_summary(self)`
- L308 `class TestCrossSectionProcessor`
- L311 `TestCrossSectionProcessor.test_winsorize_mad(self)`
- L328 `TestCrossSectionProcessor.test_winsorize_quantile(self)`
- L343 `TestCrossSectionProcessor.test_standardize_zscore(self)`
- L353 `TestCrossSectionProcessor.test_min_stocks_threshold(self)`
- L371 `class TestCostModel`
- L374 `TestCostModel.test_buy_cost(self)`
- L395 `TestCostModel.test_sell_cost(self)`
- L414 `TestCostModel.test_commission_min(self)`
- L426 `TestCostModel.test_stress_2x(self)`
- L437 `class TestTechnicalFactors`
- L440 `TestTechnicalFactors.test_reversal(self)`
- L448 `TestTechnicalFactors.test_rsi(self)`
- L458 `TestTechnicalFactors.test_macd(self)`
- L467 `TestTechnicalFactors.test_volatility(self)`
- L479 `class TestICWeighting`
- L482 `TestICWeighting.test_weight_normalization(self)`
- L501 `TestICWeighting.test_shrinkage(self)`
- L520 `TestICWeighting.test_min_obs(self)`
- L533 `TestICWeighting.test_empty_composite_score(self)`
- L545 `class TestPITUniverseAvailability`
- L548 `TestPITUniverseAvailability.test_same_day_not_available_with_lag1(self)`
- L577 `TestPITUniverseAvailability.test_next_day_available_with_lag1(self)`
- L601 `TestPITUniverseAvailability.test_future_snapshot_not_visible(self)`
- L637 `TestPITUniverseAvailability.test_query_between_snapshots_gets_latest_available(self)`
- L669 `TestPITUniverseAvailability.test_no_lag_uses_snapshot_date(self)`
- L690 `TestPITUniverseAvailability.test_available_date_uses_calendar_not_simple_addition(self)`
- L769 `class TestIndustryClassifier`
- L772 `TestIndustryClassifier.test_has_data_false_when_empty(self)`
- L779 `TestIndustryClassifier.test_has_data_true_with_static_data(self)`
- L793 `TestIndustryClassifier.test_has_pit_data_false_for_static_source(self)`
- L810 `TestIndustryClassifier.test_classifications_property_accessible(self)`
- L822 `TestIndustryClassifier.test_benchmark_industry_weights_accept_stock_weights(self)`
- L843 `class TestMemoryRegression`
- L846 `TestMemoryRegression.test_adj_factor_batch_splitting(self, tmp_path)`
- L874 `TestMemoryRegression.test_compute_adj_prices_with_explicit_df(self)`
- L906 `TestMemoryRegression.test_compute_adj_prices_rejects_explicit_empty_df(self)`
- L936 `TestMemoryRegression.test_no_cross_quarter_accumulation(self)`
- L993 `TestMemoryRegression.test_parquet_cache_covers_range_accurate(self)`
- L1036 `class TestIntegration`
- L1039 `TestIntegration.test_panel_loader_init(self)`
- L1046 `TestIntegration.test_memory_monitor(self)`
- L1055 `TestIntegration.test_cs_evaluator_empty(self)`
- L1067 `TestIntegration.test_score_to_mu_rank_only(self)`
- L1081 `TestIntegration.test_cov_estimator_empty(self)`
- L1089 `TestIntegration.test_risk_metrics_empty(self)`

## tests/test_day_gap_coverage.py

[打开文件](../../tests/test_day_gap_coverage.py)

- L19 `_write_trade_cal(tmp_path: Path, dates: list[int])`
- L30 `test_hollow_middle_detected(tmp_path: Path)`
- L60 `test_full_coverage_has_no_gaps(tmp_path: Path)`
- L78 `test_sparse_open_day_calendar_is_not_authoritative(tmp_path: Path)`
- L85 `test_calendar_missing_one_natural_day_fails_closed(tmp_path: Path)`
- L96 `test_absent_code_omitted(tmp_path: Path)`

## tests/test_diagnostic_artifacts.py

[打开文件](../../tests/test_diagnostic_artifacts.py)

- L12 `class TestDiagnosticArtifacts`
- L15 `TestDiagnosticArtifacts.test_artifacts_portfolio_values_saved(self, tmp_path)`
- L65 `TestDiagnosticArtifacts.test_benchmark_period_returns_from_compute_stats(self)`
- L104 `TestDiagnosticArtifacts.test_metrics_include_go_nogo_structured(self)`
- L143 `TestDiagnosticArtifacts.test_data_quality_gate_in_metrics(self)`

## tests/test_direct_state_allocator.py

[打开文件](../../tests/test_direct_state_allocator.py)

- L35 `_default_dsa_config()`
- L57 `_make_features_df(n_dates: int=200, vol_level: float=0.15, breadth_level: float=0.5, rng_seed: int=42)`
- L81 `class TestDirectStateAllocator`
- L84 `TestDirectStateAllocator.test_weights_sum_to_one(self)`
- L99 `TestDirectStateAllocator.test_high_vol_reduces_target_sleeve(self)`
- L114 `TestDirectStateAllocator.test_high_breadth_increases_target_sleeve(self)`
- L131 `TestDirectStateAllocator.test_high_vol_overrides_high_breadth(self)`
- L146 `TestDirectStateAllocator.test_min_warmup_respected(self)`
- L159 `TestDirectStateAllocator.test_empty_features_returns_empty(self)`
- L168 `TestDirectStateAllocator.test_missing_feature_columns_handled(self)`
- L182 `TestDirectStateAllocator.test_cap_enforced(self)`
- L198 `TestDirectStateAllocator.test_floor_enforced(self)`
- L216 `TestDirectStateAllocator.test_smoothing_limits_weekly_change(self)`
- L236 `TestDirectStateAllocator.test_pit_no_lookahead(self)`
- L276 `TestDirectStateAllocator.test_output_schema_matches_allocator(self)`
- L288 `TestDirectStateAllocator.test_diagnostic_flags_in_output(self)`
- L301 `TestDirectStateAllocator.test_available_sleeves_filtering(self)`
- L320 `TestDirectStateAllocator.test_insufficient_sleeves_returns_no_weights(self)`
- L336 `TestDirectStateAllocator.test_warmup_neutral_before_threshold(self)`
- L359 `TestDirectStateAllocator.test_rolling_quantile_nan_before_warmup(self)`
- L373 `TestDirectStateAllocator.test_available_zero_after_smoothing(self)`

## tests/test_entry_exit_attribution_matrix.py

[打开文件](../../tests/test_entry_exit_attribution_matrix.py)

- L29 `_calendar(count: int=45)`
- L36 `_case(closes: list[float], *, max_hold: int=8, stop_distance: float=0.2, suspend: set[int] | None=None, avwap: float=98.0)`
- L82 `_filled_path(values: list[float], **kwargs)`
- L93 `test_b0_entry_flags_are_frozen()`
- L105 `test_b0_v11_preserves_fill_and_sells_after_two_closes_below_c()`
- L117 `test_b0_v11_t1_red_but_above_c_does_not_fire()`
- L125 `test_b0_v11_suspend_does_not_increment_or_reset_count()`
- L134 `test_b0_v11_stop_has_priority()`
- L142 `test_boundary_exit_is_not_relabelled_as_invalidation()`
- L152 `test_b0_v12_absent_candidate_keeps_parent_exit_and_fill()`
- L162 `test_b0_v12_candidate_changes_exit_but_not_entry()`
- L172 `test_fill_freeze_rejects_mutated_entry_date()`
- L184 `test_fill_freeze_rejects_new_fill_and_unfilled_reason_change()`
- L199 `test_fill_freeze_all_filled_allows_no_terminal_reason_but_requires_entry_identity()`
- L219 `test_paired_event_statistics_rejects_different_key_coverage()`
- L232 `test_winner_retention_denominator_128_and_same_flat_rename_excluded()`
- L262 `test_dual_runtime_fixture_is_byte_identical()`
- L279 `test_runner_refuses_frozen_v10_output()`
- L298 `test_runner_rejects_draft_scope_before_historical_run(tmp_path)`
- L310 `test_draft_scope_reserves_runtime_b_b0_control_locks()`
- L328 `test_scope_reserves_new_matrix_implementation_locks()`
- L346 `test_frozen_scope_copy_hash_locks_the_runtime_b_control(tmp_path)`
- L373 `test_runtime_manifest_lock_accepts_legacy_manifest_without_dataset_field(tmp_path)`
- L393 `test_daily_metrics_discards_slots_without_any_observed_return()`
- L407 `test_baseline_replay_rejects_terminal_component_drift()`
- L427 `_runtime_gate_fixture(tmp_path: Path)`
- L458 `test_finalize_runtime_gate_requires_valid_metadata_and_records_dual_result(tmp_path)`
- L479 `test_replay_verification_includes_non_csv_outputs(tmp_path)`
- L500 `test_compiler_reads_the_six_cell_skeleton_from_frozen_controls()`
- L516 `test_historical_matrix_replaces_placeholders_instead_of_appending()`
- L541 `test_report_rejects_duplicate_matrix_cells()`
- L556 `test_report_includes_day_one_to_three_tail_columns()`

## tests/test_execution_missing_prices.py

[打开文件](../../tests/test_execution_missing_prices.py)

- L20 `_make_prices(codes, prices_dict)`
- L31 `class TestExecutionMissingPrices`
- L34 `TestExecutionMissingPrices.test_existing_position_invalid_price_kept(self)`
- L63 `TestExecutionMissingPrices.test_existing_position_invalid_price_target_differs_frozen(self)`
- L94 `TestExecutionMissingPrices.test_new_buy_no_price_stays_zero(self)`
- L119 `TestExecutionMissingPrices.test_blocked_buy_leaves_cash_not_rescaled(self)`
- L139 `TestExecutionMissingPrices.test_first_full_invest_reserves_cash_for_costs(self)`
- L159 `TestExecutionMissingPrices.test_full_name_rotate_cash_covers_recomputed_costs(self)`
- L181 `TestExecutionMissingPrices.test_shrink_buys_does_not_cut_sells(self)`
- L196 `TestExecutionMissingPrices.test_invalid_price_not_in_normalization(self)`
- L228 `TestExecutionMissingPrices.test_cost_model_skips_nan_prices(self)`
- L252 `TestExecutionMissingPrices.test_non_finite_target_weights_are_cleaned(self)`
- L273 `TestExecutionMissingPrices.test_all_prices_invalid_zero_turnover(self)`
- L301 `TestExecutionMissingPrices.test_mixed_valid_invalid_turnover_consistent(self)`

## tests/test_execution_vwap.py

[打开文件](../../tests/test_execution_vwap.py)

- L17 `test_daily_vwap_matches_close_scale()`
- L26 `test_implementation_shortfall_sign()`
- L33 `test_volume_aligned_slippage_increases_with_participation()`

## tests/test_experiment_runner.py

[打开文件](../../tests/test_experiment_runner.py)

- L13 `class TestExperimentGrid`
- L16 `TestExperimentGrid.test_build_grid_single_parameter(self, tmp_path)`
- L39 `TestExperimentGrid.test_build_grid_multi_parameter(self, tmp_path)`
- L59 `TestExperimentGrid.test_build_grid_entry_exit(self, tmp_path)`
- L79 `TestExperimentGrid.test_missing_experiment_returns_empty(self, tmp_path)`
- L94 `class TestCandidateFiltering`
- L97 `TestCandidateFiltering.test_filter_passes_all_criteria(self)`
- L125 `TestCandidateFiltering.test_filter_rejects_high_turnover(self)`
- L150 `TestCandidateFiltering.test_filter_rejects_high_fallback(self)`
- L175 `TestCandidateFiltering.test_filter_rejects_low_ir(self)`
- L200 `TestCandidateFiltering.test_filter_skips_failed(self)`
- L223 `TestCandidateFiltering.test_single_variable_experiments_dont_cross_contaminate(self)`
- L231 `class TestHelpers`
- L234 `TestHelpers.test_fmt_nan(self)`
- L237 `TestHelpers.test_fmt_none(self)`
- L240 `TestHelpers.test_fmt_valid(self)`
- L244 `class TestConfigValidation`
- L247 `TestConfigValidation.test_missing_experiments_section(self, tmp_path)`
- L257 `TestConfigValidation.test_nonexistent_config(self)`
- L266 `class TestParamForwarding`
- L269 `TestParamForwarding.test_forwards_turnover_control_params(self)`
- L297 `TestParamForwarding.test_forwards_cost_aware_params(self)`
- L320 `TestParamForwarding.test_forwards_optimizer_stability_params(self)`
- L348 `class Test2xCostFiltering`
- L351 `Test2xCostFiltering.test_candidate_rejects_bad_cost_2x(self)`
- L378 `Test2xCostFiltering.test_candidate_rejects_missing_cost_2x(self)`
- L405 `Test2xCostFiltering.test_candidate_passes_with_good_cost_2x(self)`
- L432 `Test2xCostFiltering.test_summary_includes_2x_fields(self)`
- L448 `class TestOOSSelectionIsolation`
- L451 `TestOOSSelectionIsolation.test_selection_interval_caps_at_selection_end(self)`
- L475 `TestOOSSelectionIsolation.test_selection_interval_allows_full_when_enabled(self)`
- L492 `TestOOSSelectionIsolation.test_explicit_selection_end_overrides_default(self)`
- L512 `TestOOSSelectionIsolation.test_build_bt_kwargs_uses_selection_interval(self)`
- L534 `TestOOSSelectionIsolation.test_summary_records_selection_interval(self)`

## tests/test_factor_alignment.py

[打开文件](../../tests/test_factor_alignment.py)

- L34 `_make_factor_df(factor_name: str, stocks: list=None, dates: list=None, rng_seed: int=42)`
- L58 `_default_alignment_config()`
- L70 `class TestFactorAlignment`
- L73 `TestFactorAlignment.test_monthly_factor_extended_to_weekly(self)`
- L97 `TestFactorAlignment.test_no_future_leakage(self)`
- L126 `TestFactorAlignment.test_future_values_isolated(self)`
- L162 `TestFactorAlignment.test_stale_values_dropped(self)`
- L190 `TestFactorAlignment.test_fundamental_allows_longer_stale(self)`
- L214 `TestFactorAlignment.test_no_duplicate_ts_code_per_date(self)`
- L239 `TestFactorAlignment.test_empty_factor_df_returns_empty(self)`
- L247 `TestFactorAlignment.test_multiple_factors_aligned_simultaneously(self)`
- L264 `class TestTradingDayCounter`
- L267 `TestTradingDayCounter.test_count_zero_for_same_day(self)`
- L271 `TestTradingDayCounter.test_count_excludes_start_includes_end(self)`
- L276 `TestTradingDayCounter.test_count_zero_when_from_equals_to(self)`
- L280 `TestTradingDayCounter.test_no_trade_dates_between(self)`
- L285 `class TestValuationStaleWindow`
- L288 `TestValuationStaleWindow.test_default_valuation_set_includes_ep(self)`
- L292 `TestValuationStaleWindow.test_daily_ep_dropped_when_older_than_technical_stale(self)`
- L316 `TestValuationStaleWindow.test_quarterly_roe_survives_same_gap(self)`

## tests/test_factor_cache_migration.py

[打开文件](../../tests/test_factor_cache_migration.py)

- L19 `class TestLegacyFactorCleanup`
- L22 `TestLegacyFactorCleanup.test_cleanup_legacy_factor_layout_removes_bare_files(self)`
- L66 `TestLegacyFactorCleanup.test_write_factor_auto_cleans_legacy(self)`
- L112 `TestLegacyFactorCleanup.test_cleanup_all_legacy_scans_everything(self)`
- L151 `TestLegacyFactorCleanup.test_factor_coverage_no_duplicates_after_cleanup(self)`

## tests/test_factor_candidate_v4_r2.py

[打开文件](../../tests/test_factor_candidate_v4_r2.py)

- L26 `class TestCandidatePoolConfig`
- L30 `TestCandidatePoolConfig.cfg(self)`
- L35 `TestCandidatePoolConfig.test_config_is_valid_yaml(self, cfg)`
- L41 `TestCandidatePoolConfig.test_enabled_factors_is_list(self, cfg)`
- L47 `TestCandidatePoolConfig.test_enabled_factors_exist_in_definitions(self, cfg)`
- L62 `TestCandidatePoolConfig.test_no_gate_fail_in_enabled(self, cfg)`
- L76 `TestCandidatePoolConfig.test_no_data_missing_in_enabled(self, cfg)`
- L90 `TestCandidatePoolConfig.test_watch_factors_have_justification(self, cfg)`
- L114 `TestCandidatePoolConfig.test_sha256_computable(self, cfg)`
- L120 `TestCandidatePoolConfig.test_composite_config_valid(self, cfg)`
- L127 `TestCandidatePoolConfig.test_cross_section_config_valid(self, cfg)`
- L134 `TestCandidatePoolConfig.test_disabled_factors_have_reasons(self, cfg)`
- L140 `TestCandidatePoolConfig.test_pending_gate_documented(self, cfg)`
- L159 `class TestCandidatePoolVsGate`
- L163 `TestCandidatePoolVsGate.gate_df(self)`
- L171 `TestCandidatePoolVsGate.test_gate_pass_factors_in_candidate_pool(self, gate_df)`

## tests/test_factor_gating_dynamic.py

[打开文件](../../tests/test_factor_gating_dynamic.py)

- L27 `_is_valid_ymd(d: int)`
- L36 `_generate_trade_dates(start: int, n_dates: int)`
- L46 `_make_factor_df(name, dates, stocks, seed=42)`
- L59 `_make_fwd_returns(dates, stocks, horizon=5, seed=99)`
- L76 `class TestMaturedICCutoff`
- L79 `TestMaturedICCutoff.test_basic_cutoff(self)`
- L88 `TestMaturedICCutoff.test_cross_month_boundary(self)`
- L105 `TestMaturedICCutoff.test_insufficient_history(self)`
- L116 `class TestHorizonThreading`
- L119 `TestHorizonThreading.test_custom_horizon_used_in_rolling_ic(self)`
- L135 `TestHorizonThreading.test_compute_weights_uses_trade_dates_cutoff(self)`
- L160 `TestHorizonThreading.test_yaml_horizon_defaults_to_self_horizon(self)`
- L170 `class TestCoverageGateMaturedWindow`
- L173 `TestCoverageGateMaturedWindow.test_recent_dates_excluded_from_coverage(self)`
- L203 `class TestHardCapFeasibility`
- L206 `TestHardCapFeasibility.test_min_factors_for_cap_formula(self)`
- L214 `TestHardCapFeasibility.test_two_factors_with_cap_025_rejected(self)`
- L225 `TestHardCapFeasibility.test_four_factors_all_within_cap(self)`
- L237 `TestHardCapFeasibility.test_default_config_cap_feasibility_disabled(self)`
- L250 `class TestConfigCompatibility`
- L253 `TestConfigCompatibility.test_normalize_factor_config_list_input(self)`
- L265 `TestConfigCompatibility.test_normalize_factor_config_dict_input(self)`
- L275 `TestConfigCompatibility.test_factors_config_path_default(self)`
- L288 `TestConfigCompatibility.test_factors_config_path_custom(self)`
- L306 `class TestMissingTradeDates`
- L309 `TestMissingTradeDates.test_factor_gating_without_trade_dates_returns_false(self)`

## tests/test_factor_pruning.py

[打开文件](../../tests/test_factor_pruning.py)

- L15 `_make_dates(n_dates: int=20, start_year: int=2020)`
- L26 `_make_factor_df(name: str, n_stocks: int=50, n_dates: int=20, start_year: int=2020)`
- L41 `_make_fwd_rets(n_stocks: int=50, n_dates: int=20, start_year: int=2020)`
- L56 `class TestFactorPrunerBasic`
- L59 `TestFactorPrunerBasic.test_empty_factors(self)`
- L64 `TestFactorPrunerBasic.test_no_enabled_factors(self)`
- L74 `TestFactorPrunerBasic.test_single_factor_analysis(self)`
- L89 `TestFactorPrunerBasic.test_analysis_includes_required_fields(self)`
- L104 `TestFactorPrunerBasic.test_removal_reasons_are_explicit(self)`
- L123 `TestFactorPrunerBasic.test_downweight_reasons_are_explicit(self)`
- L143 `class TestFactorPrunerDecisions`
- L146 `TestFactorPrunerDecisions.test_2025_decay_not_used_for_removal(self)`
- L178 `TestFactorPrunerDecisions.test_negative_ic_majority_removed(self)`
- L201 `TestFactorPrunerDecisions.test_low_coverage_removed(self)`
- L221 `class TestFactorPrunerReport`
- L224 `TestFactorPrunerReport.test_report_includes_removals(self)`
- L239 `TestFactorPrunerReport.test_pruned_config_structure(self)`
- L256 `TestFactorPrunerReport.test_oos_disclaimer_in_config(self)`

## tests/test_factor_quality_output_validation.py

[打开文件](../../tests/test_factor_quality_output_validation.py)

- L28 `_write_csv(tmp_path: Path, name: str, data: list[dict])`
- L35 `_write_yaml(tmp_path: Path, name: str, data: dict)`
- L41 `class TestNeutralizationValidity`
- L42 `TestNeutralizationValidity.test_low_coverage_ok_fails(self, tmp_path)`
- L51 `TestNeutralizationValidity.test_low_coverage_size_dependent_fails(self, tmp_path)`
- L60 `TestNeutralizationValidity.test_normal_coverage_passes(self, tmp_path)`
- L70 `class TestGateNeutralizationConsistency`
- L71 `TestGateNeutralizationConsistency.test_watch_neutral_only_invalid_fails(self, tmp_path)`
- L84 `TestGateNeutralizationConsistency.test_pass_invalid_neutralization_fails(self, tmp_path)`
- L98 `class TestCapacityCNYScale`
- L99 `TestCapacityCNYScale.test_market_cap_wan_scale_fails(self, tmp_path)`
- L108 `TestCapacityCNYScale.test_normal_cny_scale_passes(self, tmp_path)`
- L118 `class TestCapacityParticipation`
- L119 `TestCapacityParticipation.test_participation_formula_mismatch_fails(self, tmp_path)`
- L129 `TestCapacityParticipation.test_correct_participation_passes(self, tmp_path)`
- L140 `class TestCandidatePoolContract`
- L141 `TestCandidatePoolContract.test_log_market_cap_in_eligible_fails(self, tmp_path)`
- L153 `TestCandidatePoolContract.test_empty_eligible_no_alpha_source(self, tmp_path)`
- L170 `class TestManifestValidator`
- L173 `TestManifestValidator.test_fails_empty_manifest_start_time(self, tmp_path)`
- L196 `TestManifestValidator.test_fails_missing_required_field(self, tmp_path)`
- L219 `TestManifestValidator.test_fails_end_time_before_start_time(self, tmp_path)`
- L242 `TestManifestValidator.test_valid_manifest_passes(self, tmp_path)`
- L264 `class TestDiagnosticCsvValidator`
- L267 `TestDiagnosticCsvValidator.test_fails_diagnostic_csv_leaked_to_root(self, tmp_path)`
- L279 `TestDiagnosticCsvValidator.test_clean_root_passes(self, tmp_path)`
- L287 `TestDiagnosticCsvValidator.test_fails_missing_diagnostic_csv_in_run_dir(self, tmp_path)`
- L297 `TestDiagnosticCsvValidator.test_passes_when_all_diagnostic_csvs_present(self, tmp_path)`
- L306 `TestDiagnosticCsvValidator.test_fails_unreadable_diagnostic_csv(self, tmp_path)`

## tests/test_factor_quality_rebuild.py

[打开文件](../../tests/test_factor_quality_rebuild.py)

- L62 `_make_mock_factor_df(n_stocks: int=50, n_dates: int=200, seed: int=42, alpha_strength: float=0.02, reverse: bool=False, start_year: int=2017)`
- L89 `_make_mock_fwd_returns(factor_df: pd.DataFrame, alpha_strength: float=0.02, seed: int=42)`
- L107 `_make_mock_daily_basic(factor_df: pd.DataFrame, seed: int=99)`
- L123 `_make_mock_log_mcap(factor_df: pd.DataFrame, seed: int=77)`
- L140 `class TestICComputation`
- L141 `TestICComputation.test_rank_ic_positive_for_positive_alpha(self)`
- L151 `TestICComputation.test_rank_ic_negative_for_reversed_alpha(self)`
- L161 `TestICComputation.test_rank_ic_requires_min_30(self)`
- L167 `TestICComputation.test_pearson_ic_requires_min_30(self)`
- L178 `class TestInputAudit`
- L179 `TestInputAudit.test_empty_factor_fails(self)`
- L187 `TestInputAudit.test_constant_factor_fails(self)`
- L205 `TestInputAudit.test_duplicate_keys_fails(self)`
- L217 `TestInputAudit.test_normal_factor_passes(self)`
- L225 `TestInputAudit.test_loader_preserves_duplicate_keys_for_audit(self)`
- L244 `TestInputAudit.test_coverage_denominator_is_fwd_universe(self)`
- L264 `TestInputAudit.test_empty_cache_is_data_missing(self)`
- L272 `TestInputAudit.test_missing_rate_above_20_pct_fails(self)`
- L295 `class TestDirectionAudit`
- L296 `TestDirectionAudit.test_positive_alpha_keeps_original_direction(self)`
- L308 `TestDirectionAudit.test_reversed_alpha_flips_direction(self)`
- L319 `TestDirectionAudit.test_direction_uses_calibration_only(self)`
- L335 `class TestICByYear`
- L336 `TestICByYear.test_ic_uses_corrected_direction(self)`
- L355 `class TestQuantileReturns`
- L356 `TestQuantileReturns.test_net_spread_positive_for_strong_alpha(self)`
- L368 `TestQuantileReturns.test_high_turnover_reduces_net_spread(self)`
- L387 `class TestQualityGate`
- L388 `TestQualityGate._default_gate_cfg(self)`
- L400 `TestQualityGate._default_gate_basis_cfg(self)`
- L408 `TestQualityGate._make_passing_ic_rows(self, fname: str, basis: str, years=None)`
- L418 `TestQualityGate._make_passing_q_rows(self, fname: str, basis: str, years=None)`
- L428 `TestQualityGate.test_strong_factor_passes_gate(self)`
- L454 `TestQualityGate.test_negative_net_spread_fails_gate(self)`
- L484 `TestQualityGate.test_input_audit_fail_blocks_gate(self)`
- L497 `TestQualityGate.test_no_leakage_failure_blocks_gate(self)`
- L519 `TestQualityGate.test_raw_pass_neutral_fail_becomes_watch_size_dependent(self)`
- L555 `TestQualityGate.test_raw_fail_neutral_pass_becomes_watch_neutral_only(self)`
- L593 `TestQualityGate.test_log_market_cap_never_eligible(self)`
- L616 `TestQualityGate.test_ic_decline_downgrades_pass_to_watch(self)`
- L641 `TestQualityGate.test_rolling_window_fragile_downgrades_pass(self)`
- L673 `TestQualityGate.test_capacity_fail_blocks_pass(self)`
- L699 `TestQualityGate.test_coverage_percentage_failure(self)`
- L725 `class TestCorrelationClusters`
- L726 `TestCorrelationClusters.test_highly_correlated_factors_clustered(self)`
- L765 `TestCorrelationClusters.test_cluster_dedup_keeps_only_representative(self)`
- L797 `class TestRealTurnover`
- L798 `TestRealTurnover.test_turnover_method_is_real_weight_drift_or_overlap_proxy(self)`
- L819 `TestRealTurnover.test_real_turnover_changes_net_spread(self)`
- L846 `class TestMcapNeutralization`
- L847 `TestMcapNeutralization.test_neutralization_reduces_size_dependent_alpha(self)`
- L894 `TestMcapNeutralization.test_neutralization_with_insufficient_coverage(self)`
- L933 `class TestICTrend`
- L934 `TestICTrend.test_declining_ic_detected(self)`
- L974 `class TestRollingWindowGate`
- L975 `TestRollingWindowGate.test_four_windows_computed(self)`
- L1008 `class TestCapacityAudit`
- L1009 `TestCapacityAudit.test_capacity_identifies_low_liquidity(self)`
- L1048 `class TestCandidatePool`
- L1049 `TestCandidatePool.test_log_market_cap_excluded_from_eligible(self)`
- L1067 `TestCandidatePool.test_no_alpha_source_found_when_no_pass(self)`
- L1087 `TestCandidatePool.test_watch_never_enters_eligible(self)`
- L1106 `class TestReport`
- L1107 `TestReport.test_report_generates_without_stub(self)`
- L1120 `TestReport.test_report_contains_no_alpha_source_found_when_empty(self)`
- L1145 `class TestNoStub`
- L1146 `TestNoStub.test_no_stub_outputs_in_audit(self)`
- L1156 `TestNoStub.test_empty_cache_is_not_stub(self)`
- L1170 `class TestRegimeBreakdown`
- L1171 `TestRegimeBreakdown.test_regime_breakdown_without_files(self)`
- L1196 `class TestAmountUnitConversion`
- L1197 `TestAmountUnitConversion.test_cny_unit_no_conversion(self)`
- L1202 `TestAmountUnitConversion.test_yuan_unit_no_conversion(self)`
- L1207 `TestAmountUnitConversion.test_thousand_cny_multiplies_by_1000(self)`
- L1212 `TestAmountUnitConversion.test_wan_cny_multiplies_by_10000(self)`
- L1217 `TestAmountUnitConversion.test_unsupported_unit_raises(self)`
- L1221 `TestAmountUnitConversion.test_derived_from_circ_mv_ignores_amount_column(self)`
- L1236 `TestAmountUnitConversion.test_direct_amount_uses_configured_unit(self)`
- L1247 `TestAmountUnitConversion.test_direct_amount_unsupported_unit_raises(self)`
- L1263 `class TestNeutralizationRowCount`
- L1264 `TestNeutralizationRowCount.test_row_counts_are_real_rows_not_dates(self)`
- L1302 `class TestRunManifestStartTime`
- L1305 `TestRunManifestStartTime.test_preserves_start_time_on_success(self, tmp_path)`
- L1326 `TestRunManifestStartTime.test_preserves_start_time_on_failure(self, tmp_path)`
- L1345 `class TestRunErrorsHeaderOnly`
- L1348 `TestRunErrorsHeaderOnly.test_errors_created_header_only_on_start(self, tmp_path)`
- L1365 `TestRunErrorsHeaderOnly.test_errors_appends_without_duplicate_header(self, tmp_path)`
- L1381 `TestRunErrorsHeaderOnly.test_progress_and_timings_also_header_only(self, tmp_path)`
- L1401 `class TestPublishBoundary`
- L1404 `TestPublishBoundary.test_does_not_copy_diagnostic_csv_to_root(self, tmp_path)`
- L1445 `TestPublishBoundary.test_missing_official_csv_not_copied(self, tmp_path)`

## tests/test_factor_style_signal_validation.py

[打开文件](../../tests/test_factor_style_signal_validation.py)

- L61 `_make_synthetic_factor(n_stocks: int=100, n_dates: int=200, start_date: int=20200102, ic_signal: float=0.05, noise: float=0.02, seed: int=42)`
- L103 `_make_synthetic_fwd(factor_df: pd.DataFrame, horizon_col: str='fwd_ret_20d', ic_signal: float=0.05, noise: float=0.02, seed: int=99)`
- L131 `_make_synthetic_trading_dates(start: int, end: int)`
- L151 `class TestLookAheadBias`
- L154 `TestLookAheadBias.test_ic_mapped_to_future_available_date(self)`
- L179 `TestLookAheadBias.test_label_at_signal_date_only_uses_past_ics(self)`
- L211 `TestLookAheadBias.test_labels_shift_forward_by_horizon(self)`
- L311 `class TestICAvailableDate`
- L314 `TestICAvailableDate.test_ic_not_available_before_horizon(self)`
- L376 `class TestDateFiltering`
- L379 `TestDateFiltering.test_filter_by_date_range_removes_out_of_range(self)`
- L390 `TestDateFiltering.test_filter_empty_df(self)`
- L396 `TestDateFiltering.test_signal_dates_respect_start_end(self)`
- L418 `class TestGrowthCoverageBlocking`
- L421 `TestGrowthCoverageBlocking.test_low_coverage_detected(self)`
- L448 `TestGrowthCoverageBlocking.test_sufficient_coverage_passes(self)`
- L470 `TestGrowthCoverageBlocking.test_growth_watch_is_observation_only_when_blocked(self)`
- L544 `class TestCorrelationDedup`
- L547 `TestCorrelationDedup.test_highly_correlated_factors_dropped(self)`
- L587 `TestCorrelationDedup.test_single_factor_no_dedup(self)`
- L602 `TestCorrelationDedup.test_uncorrelated_factors_both_kept(self)`
- L629 `class TestPredictivePower`
- L632 `TestPredictivePower.test_momentum_on_no_predictive_power(self)`
- L695 `TestPredictivePower.test_momentum_on_with_predictive_power_stays_ok(self)`
- L746 `class TestOutputContract`
- L749 `TestOutputContract.test_all_output_files_produced(self, tmp_path)`
- L814 `TestOutputContract.test_yaml_has_empty_eligible_factors(self)`
- L830 `TestOutputContract.test_manifest_has_no_leakage_fields(self)`
- L847 `TestOutputContract.test_candidate_pool_schema_is_v2(self)`
- L861 `TestOutputContract.test_style_signal_status_values(self)`
- L884 `class TestRankIC`
- L887 `TestRankIC.test_rank_ic_perfect_positive(self)`
- L894 `TestRankIC.test_rank_ic_perfect_negative(self)`
- L901 `TestRankIC.test_rank_ic_insufficient_obs(self)`
- L908 `TestRankIC.test_rank_ic_with_nans(self)`
- L917 `class TestCorrelationMatrix`
- L920 `TestCorrelationMatrix.test_corr_matrix_shape(self)`
- L938 `class TestCoverageEdgeCases`
- L941 `TestCoverageEdgeCases.test_coverage_empty_factor(self)`
- L949 `TestCoverageEdgeCases.test_coverage_empty_fwd(self)`
- L957 `TestCoverageEdgeCases.test_evaluate_coverage_no_data(self)`
- L969 `class TestLabelClassification`
- L972 `TestLabelClassification.test_mixed_style_when_both_above_threshold_and_close(self)`
- L997 `TestLabelClassification.test_momentum_on_when_mom_much_higher(self)`
- L1021 `TestLabelClassification.test_no_clear_style_when_all_below_threshold(self)`

## tests/test_fetch_index_constituent_prices.py

[打开文件](../../tests/test_fetch_index_constituent_prices.py)

- L17 `test_beijing_dropped_chinext_kept()`

## tests/test_fetch_photoresist_adjusted_prices.py

[打开文件](../../tests/test_fetch_photoresist_adjusted_prices.py)

- L14 `test_adjusted_ohlc_equals_raw_times_factor()`
- L34 `test_missing_adjustment_factor_fails_closed()`
- L47 `test_duplicate_adjustment_keys_fail_closed()`

## tests/test_frozen_backtest_validation.py

[打开文件](../../tests/test_frozen_backtest_validation.py)

- L21 `class TestConfigHashes`
- L24 `TestConfigHashes.test_file_sha256_consistent(self)`
- L44 `TestConfigHashes.test_file_sha256_different(self)`
- L63 `TestConfigHashes.test_file_sha256_missing_file(self)`
- L68 `TestConfigHashes.test_factor_list_hash_consistent(self)`
- L75 `TestConfigHashes.test_factor_list_hash_different(self)`
- L81 `TestConfigHashes.test_factor_list_hash_empty(self)`
- L87 `class TestManifestMatches`
- L90 `TestManifestMatches.setup_method(self)`
- L103 `TestManifestMatches.teardown_method(self)`
- L108 `TestManifestMatches._write_manifest(self, **overrides)`
- L128 `TestManifestMatches.test_basic_match(self)`
- L167 `TestManifestMatches.test_mismatch_start_date(self)`
- L174 `TestManifestMatches.test_mismatch_end_date(self)`
- L181 `TestManifestMatches.test_mismatch_top_n(self)`
- L188 `TestManifestMatches.test_mismatch_strategy_mode(self)`
- L195 `TestManifestMatches.test_mismatch_factors_config_path(self)`
- L202 `TestManifestMatches.test_mismatch_config_hash_blocks_reuse(self)`
- L244 `TestManifestMatches.test_config_hash_match_allows_reuse(self)`
- L284 `TestManifestMatches.test_missing_manifest_file(self)`
- L290 `TestManifestMatches.test_no_hash_fields_rejected_by_default(self)`
- L316 `TestManifestMatches.test_legacy_manifest_allowed_with_flag(self)`
- L336 `TestManifestMatches.test_partial_hashes_rejected_in_strict_mode(self)`
- L384 `class TestCLIFlags`
- L387 `TestCLIFlags.test_force_overrides_reuse(self)`
- L408 `TestCLIFlags.test_default_no_reuse(self)`
- L423 `TestCLIFlags.test_reuse_existing_enables_reuse(self)`
- L437 `TestCLIFlags.test_skip_existing_backward_compat(self)`

## tests/test_go_nogo_data_gate.py

[打开文件](../../tests/test_go_nogo_data_gate.py)

- L10 `class TestGoNoGoDataGate`
- L13 `TestGoNoGoDataGate.setup_method(self)`
- L16 `TestGoNoGoDataGate.test_gate_benchmark_missing_produces_no_go_data_invalid(self)`
- L34 `TestGoNoGoDataGate.test_gate_benchmark_insufficient_produces_fail(self)`
- L49 `TestGoNoGoDataGate.test_gate_inadequate_periods_fails(self)`
- L64 `TestGoNoGoDataGate.test_gate_unstable_not_hard_fail(self)`
- L81 `TestGoNoGoDataGate.test_gate_extreme_single_period_return_fails(self)`
- L97 `TestGoNoGoDataGate.test_gate_non_finite_metrics_fail(self)`
- L111 `TestGoNoGoDataGate.test_gate_all_ok_produces_go(self)`
- L128 `TestGoNoGoDataGate.test_gate_price_quality_status_check(self)`
- L143 `TestGoNoGoDataGate.test_robustness_go_nogo_returns_overall_field(self)`

## tests/test_go_nogo_decision.py

[打开文件](../../tests/test_go_nogo_decision.py)

- L22 `class TestCheckCompleteness`
- L25 `TestCheckCompleteness.test_all_years_present(self)`
- L47 `TestCheckCompleteness.test_missing_validation_years(self)`
- L67 `TestCheckCompleteness.test_missing_ytd_years(self)`
- L83 `TestCheckCompleteness.test_no_candidate_data_at_all(self)`
- L90 `TestCheckCompleteness.test_multiple_candidates_checked_independently(self)`
- L106 `TestCheckCompleteness.test_full_complete_scenario(self)`
- L133 `class TestComputeSummary`
- L136 `TestComputeSummary.test_summary_with_full_data(self)`
- L158 `TestComputeSummary.test_empty_subset_returns_empty_dict(self)`
- L163 `TestComputeSummary.test_summary_with_negative_years(self)`
- L186 `class TestComputeSummaryDrawdown`
- L189 `TestComputeSummaryDrawdown.test_avg_max_drawdown(self)`
- L209 `TestComputeSummaryDrawdown.test_worst_max_drawdown(self)`
- L229 `TestComputeSummaryDrawdown.test_max_drawdown_columns_in_output(self)`
- L278 `class TestEvaluateThresholds`
- L281 `TestEvaluateThresholds.test_all_pass(self)`
- L293 `TestEvaluateThresholds.test_avg_excess_fails(self)`
- L305 `TestEvaluateThresholds.test_pos_years_fails(self)`
- L317 `TestEvaluateThresholds.test_avg_ir_fails(self)`
- L329 `TestEvaluateThresholds.test_max_loss_fails(self)`
- L342 `class TestR2Inclusion`
- L345 `TestR2Inclusion.test_r2_in_required_candidate_strategies(self)`
- L352 `TestR2Inclusion.test_r2_in_main_candidate_list(self)`
- L361 `TestR2Inclusion.test_missing_r2_causes_incomplete(self)`
- L381 `TestR2Inclusion.test_missing_r2_causes_rejection(self)`
- L416 `TestR2Inclusion.test_r2_missing_years_causes_incomplete(self)`
- L439 `TestR2Inclusion.test_complete_r2_data_passes(self)`
- L459 `TestR2Inclusion.test_document_contains_r2_when_present(self)`
- L497 `class TestAllowIncomplete`
- L500 `TestAllowIncomplete.test_refuses_without_allow_incomplete(self)`
- L529 `TestAllowIncomplete.test_allows_with_allow_incomplete(self)`
- L561 `TestAllowIncomplete.test_complete_data_no_warning(self)`

## tests/test_growth_factor_pit_dedup_v4_r2.py

[打开文件](../../tests/test_growth_factor_pit_dedup_v4_r2.py)

- L36 `multi_report_financial_data()`
- L67 `multi_revision_financial_data()`
- L88 `trade_dates()`
- L101 `class TestMultiReportPeriodDedup`
- L104 `TestMultiReportPeriodDedup.test_growth_ttm_multi_report_period_no_duplicates(self, multi_report_financial_data, trade_dates)`
- L127 `TestMultiReportPeriodDedup.test_keeps_latest_available_date(self, multi_report_financial_data, trade_dates)`
- L152 `TestMultiReportPeriodDedup.test_stability_8q_no_duplicates(self, multi_report_financial_data, trade_dates)`
- L165 `TestMultiReportPeriodDedup.test_earnings_acceleration_no_duplicates(self, multi_report_financial_data, trade_dates)`
- L183 `class TestAnnDateRevision`
- L186 `TestAnnDateRevision.test_keeps_latest_ann_date_not_exceeding_trade_date(self, multi_revision_financial_data, trade_dates)`
- L216 `class TestFutureLeakagePrevention`
- L219 `TestFutureLeakagePrevention.test_no_future_available_date_used(self, multi_report_financial_data, trade_dates)`
- L232 `TestFutureLeakagePrevention.test_early_trade_date_excludes_late_report(self, multi_report_financial_data, trade_dates)`
- L251 `class TestAllGrowthFactorsDedup`
- L254 `TestAllGrowthFactorsDedup.test_all_four_growth_factors_no_duplicates(self, multi_report_financial_data, trade_dates)`
- L294 `TestAllGrowthFactorsDedup.test_unique_key_assertion_would_pass(self, multi_report_financial_data, trade_dates)`

## tests/test_ic_weighting_single_factor.py

[打开文件](../../tests/test_ic_weighting_single_factor.py)

- L16 `_make_factor_df(name, dates, stocks, seed=42)`
- L30 `_make_fwd_returns(dates, stocks, horizon=5, seed=99)`
- L44 `class TestICWeightingSingleFactor`
- L47 `TestICWeightingSingleFactor.test_single_factor_produces_composite_score(self)`
- L75 `TestICWeightingSingleFactor.test_multi_factor_no_column_collision(self)`
- L100 `TestICWeightingSingleFactor.test_partial_factor_missing_on_date(self)`
- L129 `TestICWeightingSingleFactor.test_single_factor_compute_score_direct(self)`
- L161 `TestICWeightingSingleFactor.test_compute_weights_without_trade_dates_returns_empty(self)`
- L181 `TestICWeightingSingleFactor.test_cross_year_lookback_includes_previous_year(self)`

## tests/test_index_cache_code_isolation.py

[打开文件](../../tests/test_index_cache_code_isolation.py)

- L13 `test_updating_one_index_preserves_other_codes_in_same_year()`

## tests/test_index_daily_cache_strict.py

[打开文件](../../tests/test_index_daily_cache_strict.py)

- L10 `class TestIndexDailyStrictMode`
- L13 `TestIndexDailyStrictMode.test_ts_code_filter_applied(self)`
- L47 `TestIndexDailyStrictMode.test_partial_cache_returns_diag_attrs(self)`
- L89 `TestIndexDailyStrictMode.test_full_coverage_returns_data(self)`
- L128 `TestIndexDailyStrictMode.test_missing_trade_days_detected(self)`

## tests/test_index_universe_board_all_exec.py

[打开文件](../../tests/test_index_universe_board_all_exec.py)

- L18 `test_chinext_star_limit_ratios_by_regime()`
- L28 `test_tradable_uses_supplied_20pct_limits_for_star()`
- L47 `test_missing_cache_limit_synthesized_from_preclose_star()`
- L65 `test_ipo_window_blocks_new_chinext()`
- L84 `test_suspend_blocks_chinext_buy_and_sell()`
- L107 `test_local_universe_board_all_keeps_off_main(monkeypatch)`

## tests/test_index_weight_completeness.py

[打开文件](../../tests/test_index_weight_completeness.py)

- L15 `_sane_frame(n: int=50, trade_date: int=20200123, index_code: str='000819.SH')`
- L25 `_write_snapshot(cache, frame, index_code: str='000819.SH')`
- L34 `class TestIndexWeightCompleteness`
- L35 `TestIndexWeightCompleteness._client(self, tmp_path)`
- L41 `TestIndexWeightCompleteness.test_sane_cache_serves_without_api(self, tmp_path)`
- L58 `TestIndexWeightCompleteness.test_invalid_weight_schema_is_not_sane(self, mutation)`
- L73 `TestIndexWeightCompleteness.test_degenerate_trade_date_snapshot_is_not_served(self, tmp_path)`
- L99 `TestIndexWeightCompleteness.test_degenerate_api_snapshot_raises(self, tmp_path)`
- L119 `TestIndexWeightCompleteness.test_single_date_search_crosses_long_holiday(self, tmp_path)`
- L139 `TestIndexWeightCompleteness.test_range_with_degenerate_month_is_invalidated(self, tmp_path)`
- L171 `TestIndexWeightCompleteness.test_range_missing_month_raises_fail_closed(self, tmp_path)`
- L190 `TestIndexWeightCompleteness.test_range_all_months_missing_returns_empty(self, tmp_path)`

## tests/test_industry_member_pit_audit.py

[打开文件](../../tests/test_industry_member_pit_audit.py)

- L24 `test_snapshot_layout_and_lookup_agree()`
- L54 `test_change_records_make_table_latest_unsafe()`

## tests/test_limit_price_from_preclose.py

[打开文件](../../tests/test_limit_price_from_preclose.py)

- L16 `test_main_board_and_st_ratios()`
- L27 `test_tick_round_half_up()`
- L33 `test_synthesize_skips_existing_and_can_filter_board()`
- L49 `test_st_periods_from_namechange()`

## tests/test_limit_status_cache.py

[打开文件](../../tests/test_limit_status_cache.py)

- L21 `class TestLimitStatusCache`
- L24 `TestLimitStatusCache.test_parquet_cache_merge_preserves_shared_partition(self)`
- L81 `TestLimitStatusCache.test_parquet_cache_aggregate_then_write_no_dupes(self)`
- L127 `TestLimitStatusCache.test_parquet_cache_repeated_write_merges_by_key(self)`
- L168 `TestLimitStatusCache.test_single_date_cache_read_filters_by_trade_date(self)`
- L197 `class TestLimitStatusDeduplication`
- L200 `TestLimitStatusDeduplication.test_dedupe_before_cache_write(self)`

## tests/test_limit_status_cache_repair.py

[打开文件](../../tests/test_limit_status_cache_repair.py)

- L19 `class TestLimitStatusRepair`
- L22 `TestLimitStatusRepair.test_dedupe_removes_duplicates(self)`
- L43 `TestLimitStatusRepair.test_repair_preserves_partition_columns(self)`
- L61 `TestLimitStatusRepair.test_schema_normalization_helper(self)`
- L83 `TestLimitStatusRepair.test_repair_with_parquet_write_read(self)`

## tests/test_limit_status_exec_coverage.py

[打开文件](../../tests/test_limit_status_exec_coverage.py)

- L23 `test_signal_exec_pairs_match_weekly_long()`
- L38 `test_required_pairs_use_signal_pit_on_exec_date()`
- L57 `test_union_across_indices()`
- L74 `test_main_board_filter_drops_chinext_star_bj()`
- L100 `test_filter_limit_df_keeps_main_board_only()`
- L112 `test_pit_members_empty_before_first_snapshot()`
- L117 `test_snapshots_from_weights_and_present_pairs()`

## tests/test_limit_status_merge_write.py

[打开文件](../../tests/test_limit_status_merge_write.py)

- L26 `class TestLimitStatusMergeWrite`
- L29 `TestLimitStatusMergeWrite.test_short_window_does_not_reduce_dates(self)`
- L121 `TestLimitStatusMergeWrite.test_merge_write_cross_month_isolation(self)`
- L170 `TestLimitStatusMergeWrite.test_normalize_adds_year_month(self)`
- L184 `TestLimitStatusMergeWrite.test_month_bounds_correct(self)`

## tests/test_market_state_momentum_rule_validation.py

[打开文件](../../tests/test_market_state_momentum_rule_validation.py)

- L59 `_make_synthetic_dates(start: int, n: int)`
- L75 `_make_synthetic_panel(n_days: int=500, vol_mean: float=0.2, vol_std: float=0.1, breadth_mean: float=0.5, breadth_std: float=0.2, seed: int=42)`
- L98 `class TestHighVolRule`
- L101 `TestHighVolRule.test_high_vol_produces_momentum_off_research_mode(self)`
- L115 `TestHighVolRule.test_high_vol_produces_momentum_off_rolling_pit_mode(self)`
- L130 `TestHighVolRule.test_low_vol_not_momentum_off(self)`
- L148 `class TestHighBreadthRule`
- L151 `TestHighBreadthRule.test_high_breadth_low_vol_produces_momentum_on(self)`
- L170 `TestHighBreadthRule.test_high_breadth_alone_insufficient_when_vol_high(self)`
- L195 `class TestPriorityRule`
- L198 `TestPriorityRule.test_vol_priority_over_breadth(self)`
- L218 `TestPriorityRule.test_priority_order_in_rule_labels(self)`
- L235 `TestPriorityRule.test_weight_multiplier_off_is_zero(self)`
- L245 `TestPriorityRule.test_weight_multiplier_conservative_is_half(self)`
- L260 `class TestPITThresholds`
- L263 `TestPITThresholds.test_rolling_q75_only_uses_past_data(self)`
- L288 `TestPITThresholds.test_rolling_q75_increasing_with_extreme_values(self)`
- L311 `TestPITThresholds.test_rolling_pit_mode_forbidden_future_market_state(self)`
- L337 `class TestOutputContract`
- L340 `TestOutputContract.test_all_output_files_produced(self, tmp_path)`
- L466 `TestOutputContract.test_yaml_has_eligible_factors_empty(self, tmp_path)`
- L488 `TestOutputContract.test_manifest_has_no_leakage_enabled(self, tmp_path)`
- L506 `TestOutputContract.test_all_signal_labels_present_in_output(self, tmp_path)`
- L526 `class TestNegativeConclusion`
- L529 `TestNegativeConclusion.test_no_rule_alpha_when_momentum_on_fails(self)`
- L556 `TestNegativeConclusion.test_no_rule_alpha_when_off_not_worse_than_baseline(self)`
- L584 `TestNegativeConclusion.test_promoting_when_all_checks_pass(self)`
- L611 `TestNegativeConclusion.test_report_no_rule_alpha_message(self)`
- L626 `class TestMetricsComputation`
- L629 `TestMetricsComputation.test_label_metrics_insufficient_data(self)`
- L636 `TestMetricsComputation.test_label_metrics_with_valid_data(self)`
- L650 `TestMetricsComputation.test_validation_metrics_produces_all_labels(self)`
- L673 `TestMetricsComputation.test_insufficient_data_verdict(self)`
- L693 `class TestYearByYear`
- L696 `TestYearByYear.test_year_by_year_output_format(self)`
- L720 `TestYearByYear.test_year_by_year_empty_input(self)`
- L732 `class TestStrictOOS`
- L735 `TestStrictOOS.test_oos_thresholds_from_train_only(self)`
- L771 `TestStrictOOS.test_oos_thresholds_insensitive_to_test_data(self)`
- L799 `TestStrictOOS.test_oos_signal_distribution_respects_train_thresholds(self)`
- L831 `class TestWalkForward`
- L834 `TestWalkForward.test_walkforward_produces_windows(self)`
- L885 `TestWalkForward.test_walkforward_empty_on_short_data(self)`
- L907 `TestWalkForward.test_walkforward_oos_verdict_logic(self)`
- L942 `TestWalkForward.test_walkforward_stability_computed(self)`
- L979 `class TestDiscoveryTrainOnly`
- L982 `TestDiscoveryTrainOnly.test_discovery_uses_only_training_data(self)`
- L1044 `TestDiscoveryTrainOnly.test_discovery_insensitive_to_outside_data(self)`
- L1118 `class TestDiscoveryCoverageBlocked`
- L1121 `TestDiscoveryCoverageBlocked.test_coverage_blocked_factor_excluded(self)`
- L1191 `class TestNoRuleWindow`
- L1194 `TestNoRuleWindow.test_no_rule_window_all_neutral(self)`
- L1263 `class TestMultiRulePriority`
- L1266 `TestMultiRulePriority.test_negative_rule_priority_over_positive(self)`
- L1319 `TestMultiRulePriority.test_rule_sort_order(self)`
- L1387 `class TestWindowVerdict`
- L1390 `TestWindowVerdict.test_no_rule_discovered_verdict(self)`
- L1397 `TestWindowVerdict.test_pass_verdict_when_both_sides_work(self)`
- L1422 `TestWindowVerdict.test_fail_verdict_when_neither_side_works(self)`
- L1452 `class TestOverallDiscoveryVerdict`
- L1455 `TestOverallDiscoveryVerdict.test_promoting_when_enough_windows_pass(self)`
- L1507 `TestOverallDiscoveryVerdict.test_no_rule_alpha_when_few_windows(self)`
- L1544 `class TestDiscoveryOutputContract`
- L1547 `TestDiscoveryOutputContract.test_discovery_output_files_produced(self, tmp_path)`
- L1617 `TestDiscoveryOutputContract.test_discovery_yaml_has_required_fields(self, tmp_path)`
- L1637 `TestDiscoveryOutputContract.test_manifest_has_discovery_metadata(self, tmp_path)`
- L1662 `class TestVerdictResolver`
- L1665 `TestVerdictResolver.test_discovery_partial_yields_block(self)`
- L1682 `TestVerdictResolver.test_discovery_promoting_yields_promote(self)`
- L1696 `TestVerdictResolver.test_fixed_walkforward_partial_yields_block(self)`
- L1711 `TestVerdictResolver.test_strict_oos_uses_validation_results(self)`
- L1722 `TestVerdictResolver.test_in_sample_mode(self)`
- L1734 `TestVerdictResolver.test_all_non_promoting_verdicts_blocked(self)`
- L1749 `class TestOutputConsistency`
- L1752 `TestOutputConsistency.test_yaml_shows_partial_for_discovery(self, tmp_path)`
- L1884 `TestOutputConsistency.test_report_has_discovery_safe_no_leakage_text(self, tmp_path)`
- L2013 `TestOutputConsistency.test_report_has_correct_discovery_limitations(self, tmp_path)`
- L2128 `class TestResolverEmptyDiscoveryWindows`
- L2132 `TestResolverEmptyDiscoveryWindows.test_empty_discovery_windows_yields_insufficient_data(self)`
- L2164 `TestResolverEmptyDiscoveryWindows.test_empty_discovery_no_windows_key_at_all(self)`
- L2188 `TestResolverEmptyDiscoveryWindows.test_non_discovery_empty_windows_falls_back_correctly(self)`
- L2211 `TestResolverEmptyDiscoveryWindows.test_discovery_partial_with_windows_still_works(self)`
- L2238 `class TestFrozenThresholdsDates`
- L2242 `TestFrozenThresholdsDates.test_requested_train_end_stored_separately(self)`
- L2291 `TestFrozenThresholdsDates.test_test_first_observation_date_present(self)`
- L2322 `TestFrozenThresholdsDates.test_legacy_train_end_still_present(self)`

## tests/test_market_state_vs_factor_ic.py

[打开文件](../../tests/test_market_state_vs_factor_ic.py)

- L56 `_make_synthetic_dates(start: int, n: int)`
- L76 `class TestCoverageBlocked`
- L79 `TestCoverageBlocked.test_low_coverage_factor_blocked(self)`
- L102 `TestCoverageBlocked.test_coverage_blocked_factors_excluded_from_rule_candidates(self)`
- L156 `TestCoverageBlocked.test_high_coverage_factor_not_blocked(self)`
- L183 `class TestFDRCorrection`
- L186 `TestFDRCorrection.test_bh_fdr_single_test(self)`
- L196 `TestFDRCorrection.test_bh_fdr_many_tests(self)`
- L216 `TestFDRCorrection.test_bh_fdr_monotonic_in_rank(self)`
- L242 `TestFDRCorrection.test_raw_significant_but_not_fdr(self)`
- L269 `TestFDRCorrection.test_very_small_p_survives_fdr(self)`
- L295 `class TestEffectSize`
- L298 `TestEffectSize.test_small_spread_blocked(self)`
- L316 `TestEffectSize.test_large_spread_passes(self)`
- L342 `class TestRuleCandidates`
- L345 `TestRuleCandidates.test_all_gates_passed_becomes_rule_candidate(self)`
- L371 `TestRuleCandidates.test_no_direction_blocked(self)`
- L388 `TestRuleCandidates.test_insufficient_n_blocked(self)`
- L410 `class TestPITAlignment`
- L413 `TestPITAlignment.test_regime_features_use_only_pit_data(self)`
- L452 `TestPITAlignment.test_index_spread_only_uses_known_dates(self)`
- L480 `class TestOutputContract`
- L483 `TestOutputContract.test_all_output_files_produced(self, tmp_path)`
- L524 `TestOutputContract.test_rule_candidates_yaml_has_required_fields(self)`
- L550 `TestOutputContract.test_significance_adjusted_csv_has_tier_column(self)`
- L573 `class TestICAutocorrelation`
- L576 `TestICAutocorrelation.test_autocorrelation_output_format(self)`
- L594 `TestICAutocorrelation.test_autocorrelation_summary_interpretation(self)`
- L615 `TestICAutocorrelation.test_autocorrelation_insufficient_data(self)`
- L627 `TestICAutocorrelation.test_autocorrelation_with_strong_momentum(self)`
- L647 `TestICAutocorrelation.test_trailing_ic_forward_relation_insufficient(self)`
- L655 `TestICAutocorrelation.test_trailing_ic_forward_relation_with_data(self)`
- L685 `class TestConditionalICAnalysis`
- L688 `TestConditionalICAnalysis.test_conditional_ic_insufficient_data(self)`
- L697 `TestConditionalICAnalysis.test_conditional_ic_with_valid_data(self)`
- L716 `class TestRuleInterpretation`
- L719 `TestRuleInterpretation.test_rule_interpretation_uses_top_vs_bottom_spread(self)`
- L732 `TestRuleInterpretation.test_rule_interpretation_uses_spread_key_when_present(self)`
- L746 `TestRuleInterpretation.test_rule_interpretation_zero_spread_fallback(self)`

## tests/test_metrics_optimizer_diagnostics.py

[打开文件](../../tests/test_metrics_optimizer_diagnostics.py)

- L15 `class TestMetricsOptimizerDiagnostics`
- L18 `TestMetricsOptimizerDiagnostics.test_std_keys_include_optimizer_diagnostics(self)`
- L43 `TestMetricsOptimizerDiagnostics.test_phase3_optimized_metrics_include_diagnostics(self)`
- L98 `TestMetricsOptimizerDiagnostics.test_equal_weight_metrics_exclude_optimizer_diagnostics(self)`

## tests/test_ops_fault_injection.py

[打开文件](../../tests/test_ops_fault_injection.py)

- L28 `_signals(*weights: tuple[str, float])`
- L32 `_orders(signals: pd.DataFrame, status: str='READY')`
- L41 `test_stale_as_of_blocks()`
- L54 `test_duplicate_signal_blocks()`
- L62 `test_book_inventory_mismatch_blocks()`
- L80 `test_normal_rebalance_does_not_block_book_inventory()`
- L98 `test_block_leaves_book_cash_and_sends_no_orders(monkeypatch)`
- L125 `test_sell_after_mark_to_market_clears_shares()`
- L142 `test_book_weight_includes_cash_in_nav()`
- L152 `test_gated_pass_executes_same_orders_and_updates_book()`
- L190 `_scratch(name: str)`
- L199 `test_journal_restart_replay_does_not_duplicate()`
- L211 `test_paper_broker_rejects_missing_price(monkeypatch)`
- L230 `test_2017_2025_is_not_oos()`
- L243 `test_product_shadow_calls_risk_gate_check(monkeypatch)`

## tests/test_optimizer_relaxation.py

[打开文件](../../tests/test_optimizer_relaxation.py)

- L13 `class TestFeasibilityCheck`
- L16 `TestFeasibilityCheck.test_infeasible_config_detected(self)`
- L25 `TestFeasibilityCheck.test_feasible_config_passes(self)`
- L31 `TestFeasibilityCheck.test_low_optimizer_space_warning(self)`
- L38 `TestFeasibilityCheck.test_tight_but_feasible(self)`
- L47 `class TestFallbackLevels`
- L50 `TestFallbackLevels.test_relaxation_levels_recorded(self)`
- L59 `TestFallbackLevels.test_level_4_is_full_fallback(self)`
- L71 `TestFallbackLevels.test_relaxation_success_not_counted_as_fallback(self)`
- L84 `TestFallbackLevels.test_every_relaxation_has_reason(self)`
- L101 `class TestBuildFallbackWeights`
- L104 `TestBuildFallbackWeights.test_equal_weight_fallback(self)`
- L116 `TestBuildFallbackWeights.test_previous_weight_fallback(self)`
- L127 `TestBuildFallbackWeights.test_previous_with_new_stocks(self)`
- L139 `class TestDiagnosticStructure`
- L142 `TestDiagnosticStructure.test_make_diag_defaults(self)`
- L156 `TestDiagnosticStructure.test_solver_name_in_fallback_reason(self)`
- L166 `class TestEnhanceShrinkage`
- L169 `TestEnhanceShrinkage.test_enhance_shrinkage_preserves_psd(self)`
- L184 `TestEnhanceShrinkage.test_ensure_psd_fixes_non_psd(self)`
- L195 `class TestNoTradeBand`
- L198 `TestNoTradeBand.test_small_changes_use_previous_weights(self)`
- L210 `TestNoTradeBand.test_large_changes_trigger_trade(self)`
- L221 `TestNoTradeBand.test_renormalizes_to_one(self)`
- L231 `class TestMaxWeightChange`
- L234 `TestMaxWeightChange.test_weights_sum_to_one_after_cap(self)`
- L249 `class TestCovarianceShrinkageMethods`
- L252 `TestCovarianceShrinkageMethods.test_diagonal_shrink_20_supported(self)`
- L272 `TestCovarianceShrinkageMethods.test_diagonal_shrink_40_supported(self)`
- L286 `TestCovarianceShrinkageMethods.test_experiment_config_cov_methods_are_supported(self)`
- L307 `class TestConstraintRelaxationModes`
- L310 `TestConstraintRelaxationModes.test_relaxation_none_does_not_try_tiered(self)`
- L318 `TestConstraintRelaxationModes.test_relaxation_tiered_records_relaxation_level(self)`
- L333 `TestConstraintRelaxationModes.test_backtester_forwards_constraint_relaxation(self)`
- L346 `class TestTieredRelaxationNoTypeError`
- L349 `TestTieredRelaxationNoTypeError.test_l0_fallback_l1_success_no_typeerror(self)`
- L372 `TestTieredRelaxationNoTypeError.test_l0_l1_fallback_l2_success_no_typeerror(self)`
- L381 `TestTieredRelaxationNoTypeError.test_l0_l1_l2_fallback_l3_success_no_typeerror(self)`
- L390 `TestTieredRelaxationNoTypeError.test_cost_aware_params_in_every_solver_call(self)`
- L405 `TestTieredRelaxationNoTypeError.test_compute_optimized_weights_tiered_runs_end_to_end(self)`

## tests/test_output_encoding.py

[打开文件](../../tests/test_output_encoding.py)

- L15 `class TestSafePrint`
- L18 `TestSafePrint.test_safe_print_unicode_fallback(self)`
- L33 `TestSafePrint.test_safe_print_normal_text(self)`
- L41 `TestSafePrint.test_report_markdown_no_unicode_chars(self)`
- L89 `class TestSmokeStatusClassification`
- L92 `TestSmokeStatusClassification.test_smoke_short_window_phase2_data_insufficient(self)`
- L110 `TestSmokeStatusClassification.test_smoke_full_window_not_short(self)`
- L127 `TestSmokeStatusClassification.test_smoke_borderline_window(self)`

## tests/test_p0_alignment_rules.py

[打开文件](../../tests/test_p0_alignment_rules.py)

- L13 `test_ep_is_valuation_zero_lag()`
- L23 `test_roe_is_pit_aligned_not_double_lagged()`
- L33 `test_industry_classifier_starts_without_pit_flag()`

## tests/test_panic_ab_pretrade_predictor.py

[打开文件](../../tests/test_panic_ab_pretrade_predictor.py)

- L23 `make_calendar(start=20170103, n_days=2000)`
- L30 `make_samples(with_label_available=True, calendar=None)`
- L67 `test_validate_features_rejects_future_fields()`
- L76 `test_validate_features_allows_price_features()`
- L80 `test_assign_drop_ab_labels_excludes_m_and_unclassified()`
- L96 `test_load_factor_raises_on_available_date_gt_trade_date(tmp_path)`
- L110 `test_first_trading_day_of_year_strict()`
- L121 `test_first_trading_day_of_year_no_test_calendar_handled()`
- L130 `test_walkforward_windows_strictly_forward()`
- L137 `test_walkforward_no_test_calendar_status()`
- L151 `test_walkforward_output_contract_v2()`
- L184 `test_date_rank_strategies_present()`
- L202 `test_leakage_audit_split_fields()`
- L222 `test_label_availability_filter_satisfies_constraint()`
- L242 `test_price_feature_columns_excludes_daily_basic()`
- L250 `test_report_v2_contains_required_sections()`
- L288 `test_report_includes_baseline_and_raw()`
- L315 `test_summarize_status_uses_min_coverage_param()`
- L337 `test_strategy_compare_includes_raw_and_baseline()`
- L351 `test_strategy_compare_has_all_11_strategies()`
- L370 `test_diagnostics_output_exists()`
- L385 `test_report_contains_auc_diagnostic_section()`
- L410 `test_manifest_block_reasons_on_no_predictive_power()`
- L425 `test_baseline_diagnostics_uses_baseline_action()`
- L445 `test_baseline_diagnostics_matches_strategy_compare()`
- L464 `test_baseline_diagnostics_raises_on_mismatch()`

## tests/test_panic_basket_daily_gate.py

[打开文件](../../tests/test_panic_basket_daily_gate.py)

- L58 `sample_prices()`
- L75 `sample_factor()`
- L94 `sample_prices_many()`
- L110 `sample_daily_basket(sample_prices, sample_factor)`
- L166 `class TestEventRatio`
- L167 `TestEventRatio.test_event_ratio_not_always_one(self, sample_daily_basket)`
- L180 `TestEventRatio.test_event_ratio_less_than_one_with_many_stocks(self, sample_prices_many)`
- L207 `TestEventRatio.test_event_ratio_in_range(self, sample_daily_basket)`
- L213 `TestEventRatio.test_event_count_le_total_stocks(self, sample_daily_basket)`
- L219 `TestEventRatio.test_event_ratio_denominator_from_market(self, sample_daily_basket)`
- L228 `TestEventRatio.test_given_10_events_100_stocks_ratio_is_0_1(self)`
- L244 `class TestLabelAvailableDate`
- L245 `TestLabelAvailableDate.test_basket_label_available_date_is_max(self, sample_daily_basket)`
- L252 `TestLabelAvailableDate.test_basket_label_available_date_present(self, sample_daily_basket)`
- L256 `TestLabelAvailableDate.test_n_label_available_consistent(self, sample_daily_basket)`
- L269 `class TestWalkForwardSplit`
- L270 `TestWalkForwardSplit.test_label_availability_filter(self, sample_daily_basket)`
- L283 `TestWalkForwardSplit.test_embargo_drops_samples(self, sample_daily_basket)`
- L295 `TestWalkForwardSplit.test_leakage_audit_has_required_fields(self, sample_daily_basket)`
- L312 `TestWalkForwardSplit.test_validate_leakage_audit_pass(self)`
- L324 `TestWalkForwardSplit.test_validate_leakage_audit_fail(self)`
- L339 `class TestThresholdSource`
- L340 `TestThresholdSource.test_train_quantile_used(self, sample_daily_basket)`
- L369 `TestThresholdSource.test_no_test_quantile_used(self, sample_daily_basket)`
- L396 `class TestGateLabelExclusion`
- L397 `TestGateLabelExclusion.test_gate_label_not_in_whitelist(self)`
- L402 `TestGateLabelExclusion.test_strategy_extraction_excludes_gate_label(self)`
- L413 `TestGateLabelExclusion.test_gate_label_handling_in_dataframe(self)`
- L429 `class TestMLFeatureSelection`
- L430 `TestMLFeatureSelection.test_select_features_uses_train_only(self, sample_daily_basket)`
- L449 `TestMLFeatureSelection.test_feature_selection_audit_fields(self, sample_daily_basket)`
- L465 `TestMLFeatureSelection.test_future_year_columns_dont_affect_selection(self, sample_daily_basket)`
- L491 `class TestPrimaryStrategyLogic`
- L492 `TestPrimaryStrategyLogic.test_primary_strategy_frozen(self)`
- L499 `TestPrimaryStrategyLogic.test_primary_not_candidate_best(self)`
- L530 `class TestReportDisclaimers`
- L531 `TestReportDisclaimers.test_event_forward_has_no_annualized_metrics(self)`
- L544 `TestReportDisclaimers.test_path_metrics_has_annualized_metrics(self)`
- L560 `class TestPathSimulation`
- L561 `TestPathSimulation.test_exec_date_map(self, sample_prices)`
- L569 `TestPathSimulation.test_trading_day_offset(self, sample_prices)`
- L578 `TestPathSimulation.test_tranche_limit(self)`
- L591 `class TestImports`
- L592 `TestImports.test_all_gate_scripts_importable(self)`
- L606 `TestImports.test_shared_module_exports(self)`

## tests/test_panic_basket_real_path.py

[打开文件](../../tests/test_panic_basket_real_path.py)

- L35 `class TestNoApproximationFormula`
- L36 `TestNoApproximationFormula.test_real_path_uses_stock_returns(self)`
- L41 `TestNoApproximationFormula.test_real_path_function_requires_event_stock_samples(self)`
- L50 `TestNoApproximationFormula.test_no_basket_mean_ret_division(self)`
- L57 `TestNoApproximationFormula.test_fixed_capital_tranche_return_scaling(self)`
- L97 `inspect_getsource(fn)`
- L109 `class TestTrancheConstituents`
- L110 `TestTrancheConstituents.test_tranche_audit_has_stock_list(self)`
- L116 `TestTrancheConstituents.test_event_stock_samples_has_required_columns(self)`
- L130 `TestTrancheConstituents.test_tranche_audit_file_exists(self)`
- L146 `TestTrancheConstituents.test_tranche_constituents_are_stock_level(self)`
- L177 `class TestExecutionDates`
- L178 `TestExecutionDates.test_exec_date_after_signal_date(self)`
- L197 `class TestExitDateSpacing`
- L198 `TestExitDateSpacing.test_exit_date_later_than_exec_date(self)`
- L217 `class TestTrancheLimits`
- L218 `TestTrancheLimits.test_active_tranches_within_limit(self)`
- L236 `class TestExposureLimits`
- L237 `TestExposureLimits.test_gross_exposure_within_limit(self)`
- L250 `TestExposureLimits.test_gross_return_consistent_with_exposure(self)`
- L275 `class TestCostTiming`
- L276 `TestCostTiming.test_cost_not_daily_flat(self)`
- L292 `TestCostTiming.test_entry_cost_in_tranche_audit(self)`
- L310 `class TestRealPathOutputColumns`
- L311 `TestRealPathOutputColumns.test_daily_returns_has_required_columns(self)`
- L330 `TestRealPathOutputColumns.test_tranche_audit_realized_path_is_filled(self)`
- L353 `TestRealPathOutputColumns.test_real_path_compare_has_no_event_forward_mix(self)`

## tests/test_panic_gate_calendar_and_outputs.py

[打开文件](../../tests/test_panic_gate_calendar_and_outputs.py)

- L32 `class TestMarketCalendar`
- L33 `TestMarketCalendar.test_load_market_calendar_returns_data(self)`
- L42 `TestMarketCalendar.test_market_calendar_larger_than_basket(self)`
- L56 `TestMarketCalendar.test_leakage_audit_has_calendar_source(self)`
- L68 `TestMarketCalendar.test_leakage_audit_has_calendar_is_full_market(self)`
- L78 `TestMarketCalendar.test_leakage_audit_has_embargo_cutoff_date(self)`
- L88 `TestMarketCalendar.test_embargo_uses_real_trading_days(self)`
- L101 `TestMarketCalendar.test_calendar_n_days_recorded(self)`
- L119 `class TestDeprecatedOutputs`
- L120 `TestDeprecatedOutputs.test_old_backtest_compare_not_in_main_dir(self)`
- L126 `TestDeprecatedOutputs.test_old_daily_signals_not_in_main_dir(self)`
- L132 `TestDeprecatedOutputs.test_old_yearly_attribution_not_in_main_dir(self)`
- L138 `TestDeprecatedOutputs.test_deprecated_dir_exists(self)`
- L145 `TestDeprecatedOutputs.test_deprecated_manifest_exists(self)`
- L152 `TestDeprecatedOutputs.test_deprecated_manifest_valid(self)`
- L170 `class TestFinalManifest`
- L171 `TestFinalManifest.test_final_manifest_exists(self)`
- L178 `TestFinalManifest.test_final_manifest_has_required_fields(self)`
- L196 `TestFinalManifest.test_final_manifest_research_only(self)`
- L206 `TestFinalManifest.test_final_manifest_primary_strategy(self)`
- L216 `TestFinalManifest.test_final_manifest_status_consistent_with_audit(self)`
- L233 `TestFinalManifest.test_final_manifest_lists_valid_files(self)`
- L247 `TestFinalManifest.test_final_manifest_deprecated_files_match_actual(self)`

## tests/test_panic_reversal.py

[打开文件](../../tests/test_panic_reversal.py)

- L13 `make_prices(data_dict)`
- L27 `class TestThresholdBoundaries`
- L30 `TestThresholdBoundaries.test_drop_inclusive_lower_bound(self)`
- L43 `TestThresholdBoundaries.test_drop_just_above_threshold(self)`
- L54 `TestThresholdBoundaries.test_up_inclusive_upper_bound(self)`
- L66 `class TestDirectionSigns`
- L69 `TestDirectionSigns.test_drop_bin_positive(self)`
- L74 `TestDirectionSigns.test_drop_cont_positive(self)`
- L80 `TestDirectionSigns.test_up_bin_negative(self)`
- L86 `TestDirectionSigns.test_up_cont_negative(self)`
- L93 `TestDirectionSigns.test_sym_drop_positive_up_negative(self)`
- L105 `TestDirectionSigns.test_sym_cont_drop_positive_up_negative(self)`
- L118 `class TestNonEventZero`
- L121 `TestNonEventZero.test_no_event_zero(self)`
- L128 `TestNonEventZero.test_missing_price_dropped(self)`
- L139 `class TestWinsor`
- L142 `TestWinsor.test_wcont_doesnt_touch_zero(self)`
- L152 `TestWinsor.test_wcont_clips_nonzero(self)`
- L170 `class TestWeeklyFrequency`
- L173 `TestWeeklyFrequency.test_weekly_output(self)`
- L195 `class TestEmptyEdgeCases`
- L198 `TestEmptyEdgeCases.test_empty_prices(self)`
- L202 `TestEmptyEdgeCases.test_no_events(self)`
- L209 `class TestYearLoopBug`
- L213 `TestYearLoopBug.test_unique_years_not_per_row(self)`
- L229 `TestYearLoopBug.test_val_pos_years_bounded(self)`
- L247 `class TestLag1ReturnOutlierFilter`
- L250 `TestLag1ReturnOutlierFilter.test_outlier_abs_above_05_flagged(self)`
- L262 `TestLag1ReturnOutlierFilter.test_close_negative_or_zero_flagged(self)`
- L272 `TestLag1ReturnOutlierFilter.test_boundary_missing_drops(self)`
- L289 `class TestAlignmentTradeDayGap`
- L292 `TestAlignmentTradeDayGap.test_calendar_gap_uses_datetime_not_int_subtraction(self)`
- L307 `TestAlignmentTradeDayGap.test_trade_day_gap_is_one(self)`
- L318 `TestAlignmentTradeDayGap.test_holiday_gap_larger_than_one(self)`
- L329 `class TestFormalGateUsesLag1`
- L332 `TestFormalGateUsesLag1.test_execution_lag_in_summary_fields(self)`
- L348 `TestFormalGateUsesLag1.test_same_day_return_not_allowed_as_default(self)`
- L354 `TestFormalGateUsesLag1.test_lag1_parquet_has_correct_column(self)`
- L365 `class TestCostLiquidityOutput`
- L368 `TestCostLiquidityOutput.test_cost_liquidity_csv_exists_and_non_empty(self)`
- L382 `TestCostLiquidityOutput.test_cost_liquidity_has_cost_scenarios(self)`
- L390 `TestCostLiquidityOutput.test_cost_liquidity_has_mv_buckets(self)`
- L401 `class TestRegimeFactorAndSourceFields`
- L404 `TestRegimeFactorAndSourceFields.test_regime_csv_has_correct_fields(self)`
- L413 `TestRegimeFactorAndSourceFields.test_regime_factor_is_real_factor_name(self)`
- L426 `TestRegimeFactorAndSourceFields.test_regime_source_separate_from_factor(self)`
- L436 `TestRegimeFactorAndSourceFields.test_diagnostic_only_is_true(self)`
- L446 `class TestWalkforwardSelectedOutput`
- L449 `TestWalkforwardSelectedOutput.test_walkforward_selected_csv_exists(self)`
- L456 `TestWalkforwardSelectedOutput.test_walkforward_selected_has_required_fields(self)`
- L470 `TestWalkforwardSelectedOutput.test_walkforward_four_windows(self)`
- L479 `TestWalkforwardSelectedOutput.test_walkforward_selected_one_factor_per_window(self)`
- L488 `TestWalkforwardSelectedOutput.test_walkforward_candidates_csv_exists(self)`
- L495 `TestWalkforwardSelectedOutput.test_selected_factor_in_candidates(self)`
- L510 `class TestMultipleTestingOutput`
- L513 `TestMultipleTestingOutput.test_multiple_testing_csv_exists(self)`
- L520 `TestMultipleTestingOutput.test_multiple_testing_required_fields(self)`
- L533 `TestMultipleTestingOutput.test_multiple_testing_n_candidates_27(self)`
- L544 `TestMultipleTestingOutput.test_multiple_testing_n_permutations_ge_500(self)`
- L559 `class TestFastCheckDoesNotOverwriteFormal`
- L562 `TestFastCheckDoesNotOverwriteFormal.test_fast_check_output_in_debug_dir(self)`
- L569 `TestFastCheckDoesNotOverwriteFormal.test_fast_check_does_not_overwrite_formal_summary(self)`
- L588 `class TestOutputFileCompleteness`
- L606 `TestOutputFileCompleteness.test_all_required_files_exist(self)`

## tests/test_paper_broker_summary.py

[打开文件](../../tests/test_paper_broker_summary.py)

- L15 `class TestPaperBrokerSummary`
- L18 `TestPaperBrokerSummary.test_high_slippage_counted_as_executed(self)`
- L40 `TestPaperBrokerSummary.test_mixed_statuses_correctly_counted(self)`
- L60 `TestPaperBrokerSummary.test_slippage_computed_when_assumed_and_actual_differ(self)`
- L77 `TestPaperBrokerSummary.test_no_slippage_when_prices_equal(self)`

## tests/test_per_code_coverage.py

[打开文件](../../tests/test_per_code_coverage.py)

- L13 `_authoritative_calendar(start: str, end: str)`
- L23 `class TestFinancialTablePrimaryKeys`
- L27 `TestFinancialTablePrimaryKeys._cache(self, tmp_path)`
- L31 `TestFinancialTablePrimaryKeys.test_income_like_frame_write_read_roundtrip(self, tmp_path)`
- L46 `TestFinancialTablePrimaryKeys.test_income_dedup_keeps_last_per_key(self, tmp_path)`
- L70 `TestFinancialTablePrimaryKeys.test_cashflow_and_balancesheet_keyed_by_ann_date_end_date(self, tmp_path)`
- L84 `TestFinancialTablePrimaryKeys.test_industry_pit_index_code_key_with_ts_code_alias(self, tmp_path)`
- L103 `TestFinancialTablePrimaryKeys.test_unregistered_table_missing_key_columns_still_raises(self, tmp_path)`
- L111 `class TestCoversRangePerCode`
- L114 `TestCoversRangePerCode._cache(self, tmp_path)`
- L118 `TestCoversRangePerCode.test_reports_per_code_spans(self, tmp_path)`
- L138 `TestCoversRangePerCode.test_missing_table_returns_empty(self, tmp_path)`
- L144 `class TestGetDailyPerCodeCoverage`
- L147 `TestGetDailyPerCodeCoverage._client(self, tmp_path)`
- L154 `TestGetDailyPerCodeCoverage._write_prices_cache(cache, rows)`
- L161 `TestGetDailyPerCodeCoverage.test_partial_per_code_cache_is_not_served(self, tmp_path)`
- L191 `TestGetDailyPerCodeCoverage.test_full_per_code_cache_is_served_without_api(self, tmp_path)`
- L219 `TestGetDailyPerCodeCoverage.test_hollow_middle_is_not_served_from_cache(self, tmp_path)`
- L252 `TestGetDailyPerCodeCoverage.test_post_api_partial_response_raises_fail_closed(self, tmp_path)`
- L272 `TestGetDailyPerCodeCoverage.test_post_api_absent_code_raises_fail_closed(self, tmp_path)`
- L292 `TestGetDailyPerCodeCoverage.test_listing_window_and_suspension_are_not_false_gaps(self, tmp_path)`
- L339 `TestGetDailyPerCodeCoverage.test_missing_stock_status_is_loaded_before_active_day_check(self, tmp_path)`
- L382 `class TestExactMarketCodeSets`
- L383 `TestExactMarketCodeSets.test_mapping_string_is_one_code_not_characters(self, tmp_path)`
- L392 `TestExactMarketCodeSets.test_duplicate_business_key_is_rejected(self)`
- L407 `class TestFetchManifestPerCodeSpans`
- L410 `TestFetchManifestPerCodeSpans.test_spans_reaching_end_prove_coverage(self, tmp_path)`
- L423 `TestFetchManifestPerCodeSpans.test_early_span_end_means_no_coverage(self, tmp_path)`
- L436 `TestFetchManifestPerCodeSpans.test_late_span_start_means_no_coverage(self, tmp_path)`
- L446 `TestFetchManifestPerCodeSpans.test_chunked_spans_preserve_both_boundaries(self, tmp_path)`
- L460 `TestFetchManifestPerCodeSpans.test_disjoint_spans_do_not_cover_the_interior_gap(self, tmp_path)`
- L476 `TestFetchManifestPerCodeSpans.test_legacy_range_only_entries_fail_per_code_check(self, tmp_path)`
- L485 `TestFetchManifestPerCodeSpans.test_missing_code_fails_even_with_other_spans(self, tmp_path)`

## tests/test_phase0_report_validation.py

[打开文件](../../tests/test_phase0_report_validation.py)

- L15 `_tables()`
- L64 `_run(tmp_path, monkeypatch, mutate_overlap)`
- L81 `test_duplicate_substitute_months_cannot_pass(tmp_path, monkeypatch)`
- L88 `test_wrong_union_or_weight_overlap_cannot_pass(tmp_path, monkeypatch)`
- L96 `test_snapshot_rejects_negative_weights_and_duplicate_keys()`

## tests/test_phase0b_data_audit.py

[打开文件](../../tests/test_phase0b_data_audit.py)

- L17 `_weights(index_code='IDX', trade_date=20231229, count=5)`
- L26 `_market_tables(codes, calendar, path=None)`
- L53 `test_monthly_membership_rejects_multiple_snapshot_dates()`
- L66 `test_overlap_requires_synchronous_snapshot_dates_and_computes_weights()`
- L85 `test_tradability_fails_when_active_traded_member_has_no_limit_row()`
- L102 `test_pretrade_amount_is_converted_from_thousand_cny_once()`
- L147 `test_lithium_template_remains_blocked_when_evidence_is_missing()`
- L156 `test_runtime_table_gzip_is_byte_deterministic(tmp_path)`
- L174 `test_fetcher_reads_fallback_fragment_without_api_call(tmp_path)`

## tests/test_phase2_price_quality_precheck.py

[打开文件](../../tests/test_phase2_price_quality_precheck.py)

- L9 `class DummyLoader`
- L10 `DummyLoader.__init__(self, prices_adj, index_weight=None)`
- L14 `DummyLoader.query(self, table_name, columns=None, start_date=None, end_date=None, ts_codes=None)`
- L33 `test_phase2_price_quality_precheck_passes_clean_prices(tmp_path, monkeypatch)`
- L51 `test_phase2_price_quality_precheck_blocks_adj_factor_regime_break(tmp_path, monkeypatch)`
- L76 `test_phase2_price_quality_precheck_ignores_non_universe_extreme_rows(tmp_path, monkeypatch)`
- L100 `test_phase2_price_quality_precheck_still_blocks_universe_extreme_rows(tmp_path, monkeypatch)`

## tests/test_phase3_failure_metrics.py

[打开文件](../../tests/test_phase3_failure_metrics.py)

- L28 `_weekly_dates(start_str: str, n: int)`
- L33 `_monthly_dates(start_str: str, n: int)`
- L38 `_add_days(d: int, n: int)`
- L42 `_td_between(start, end)`
- L52 `_make_composite_df(signal_dates_int, n_stocks=100)`
- L64 `_make_mu_df(signal_dates_int, n_stocks=100)`
- L76 `_build_mocks(rr, signal_dates, composite_df, mu_df, loader=None)`
- L107 `class TestPhase3FailureMetrics`
- L110 `TestPhase3FailureMetrics.test_failure_metrics_contain_status_fail(self)`
- L211 `TestPhase3FailureMetrics.test_failure_metrics_overwrite_old_success(self)`
- L258 `TestPhase3FailureMetrics.test_price_precheck_failure_writes_metrics(self)`
- L339 `class TestPhase3FailureMetricsFields`
- L342 `TestPhase3FailureMetricsFields.test_fail_metrics_include_fallback_diagnostics(self)`
- L377 `TestPhase3FailureMetricsFields.test_whitelist_includes_all_failure_fields(self)`

## tests/test_phase3_price_precheck.py

[打开文件](../../tests/test_phase3_price_precheck.py)

- L29 `_weekly_dates(start_str: str, n: int)`
- L35 `_monthly_dates(start_str: str, n: int)`
- L41 `_add_days(d: int, n: int)`
- L46 `_td_between(start, end)`
- L57 `_make_composite_df(signal_dates_int, n_stocks=100)`
- L71 `_make_mu_df(signal_dates_int, n_stocks=100)`
- L84 `_build_base_mocks(rr, signal_dates, composite_df, mu_df, loader=None)`
- L116 `class TestPhase3PricePrecheck`
- L120 `TestPhase3PricePrecheck._make_fake_args(self)`
- L130 `TestPhase3PricePrecheck.test_only_2016_prices_precheck_fails(self)`
- L198 `TestPhase3PricePrecheck.test_coverage_below_95pct_fails(self)`
- L256 `class TestPhase3PricePrecheckMissingDates`
- L259 `TestPhase3PricePrecheckMissingDates.test_more_than_5_missing_dates_fails(self)`

## tests/test_phase3_validation.py

[打开文件](../../tests/test_phase3_validation.py)

- L17 `class TestPhase3HardValidation`
- L20 `TestPhase3HardValidation._make_fake_args(self)`
- L31 `TestPhase3HardValidation.test_phase3_fails_on_error_in_opt_results(self)`
- L115 `TestPhase3HardValidation.test_phase3_fails_on_opt_n_total_zero(self)`
- L198 `class TestPhase3FallbackThreshold`
- L201 `TestPhase3FallbackThreshold.test_phase3_fails_on_fallback_rate_above_20pct(self)`
- L296 `class TestPhase3PriceCacheCheck`
- L299 `TestPhase3PriceCacheCheck.test_phase3_fails_on_price_cache_insufficient(self)`
- L381 `class TestOptimizerReturnMatrix`
- L384 `TestOptimizerReturnMatrix.test_log_return_matrix_keeps_partially_observed_dates(self)`
- L407 `TestOptimizerReturnMatrix.test_ensure_psd_cleans_non_finite_covariance(self)`

## tests/test_phase5_core_suite.py

[打开文件](../../tests/test_phase5_core_suite.py)

- L11 `_phase5_args(end='20260604')`
- L33 `_successful_bt_result(excess=0.04, ir=0.4, turnover=0.2)`
- L45 `_run_phase5_with_mocks(rr, args, bt_results, phase3_base=None)`
- L97 `test_phase5_core_uses_optimized_base_config(tmp_path, monkeypatch)`
- L131 `test_phase5_core_marks_oos_missing_when_end_before_oos(tmp_path, monkeypatch)`
- L153 `test_phase5_core_reuses_matching_phase3_base(tmp_path, monkeypatch)`
- L171 `test_phase5_core_uses_custom_oos_dates(tmp_path, monkeypatch)`
- L196 `test_load_matching_phase3_optimized_requires_exact_config(tmp_path, monkeypatch)`
- L264 `test_cli_parser_includes_all_new_params()`
- L277 `test_strategy_kwargs_helper_exists()`
- L293 `test_phase5_reuse_rejects_mismatched_cost_aware_lambda()`
- L314 `test_phase5_reuse_rejects_mismatched_cov_shrinkage()`
- L329 `test_phase5_reuse_accepts_matching_new_params()`
- L353 `test_phase5_calibrate_receives_horizon_from_composite_params()`
- L424 `test_phase5_diagnostics_calibrate_receives_horizon()`

## tests/test_phase5_diagnostics.py

[打开文件](../../tests/test_phase5_diagnostics.py)

- L23 `class TestTurnoverDecomposition`
- L26 `TestTurnoverDecomposition.test_empty_data_returns_data_missing(self)`
- L31 `TestTurnoverDecomposition.test_basic_turnover_stats(self)`
- L47 `TestTurnoverDecomposition.test_high_turnover_date_identified(self)`
- L62 `TestTurnoverDecomposition.test_is_oos_separation(self)`
- L80 `TestTurnoverDecomposition.test_empty_data_does_not_report_zero_turnover(self)`
- L87 `class TestCostAttribution`
- L90 `TestCostAttribution.test_empty_data_returns_data_missing(self)`
- L95 `TestCostAttribution.test_cost_drag_computation(self)`
- L140 `TestCostAttribution.test_insufficient_periods(self)`
- L147 `TestCostAttribution.test_cost_decomposition_adds_up(self)`
- L170 `class TestFallbackAnalysis`
- L173 `TestFallbackAnalysis.test_empty_diagnostics(self)`
- L177 `TestFallbackAnalysis.test_no_optimizer_runs(self)`
- L181 `TestFallbackAnalysis.test_fallback_rate_computation(self)`
- L197 `TestFallbackAnalysis.test_reason_classification(self)`
- L210 `TestFallbackAnalysis.test_unknown_rate_hard_flag(self)`
- L227 `class TestPhase5Diagnostics`
- L230 `TestPhase5Diagnostics.test_run_all_with_empty_data(self)`
- L240 `TestPhase5Diagnostics.test_report_generation_handles_missing_data(self)`
- L247 `TestPhase5Diagnostics.test_json_export(self, tmp_path)`
- L258 `TestPhase5Diagnostics.test_fallback_csv_export(self, tmp_path)`
- L270 `TestPhase5Diagnostics.test_turnover_csv_export(self, tmp_path)`
- L289 `class TestFactorStability`
- L292 `TestFactorStability.test_empty_factors(self)`
- L296 `TestFactorStability.test_no_signal_dates(self)`
- L307 `class TestBacktestDiagnosticsPayload`
- L310 `TestBacktestDiagnosticsPayload.test_payload_present_when_enabled(self)`
- L319 `TestBacktestDiagnosticsPayload.test_payload_absent_by_default(self)`
- L327 `TestBacktestDiagnosticsPayload.test_diagnostics_uses_backtest_payload(self)`
- L350 `TestBacktestDiagnosticsPayload.test_metrics_summary_excludes_payload(self)`
- L367 `class TestFallbackEvents`
- L370 `TestFallbackEvents.test_opt_events_include_signal_date_and_reason(self)`
- L388 `TestFallbackEvents.test_fallback_csv_uses_event_level_logs(self)`
- L435 `TestFallbackEvents.test_fallback_csv_falls_back_to_aggregate(self)`
- L458 `class TestDiagnosticsDryRun`
- L461 `TestDiagnosticsDryRun.test_dry_run_returns_zero(self)`
- L472 `TestDiagnosticsDryRun.test_dry_run_does_not_call_loader(self)`
- L491 `class TestExecutionRules`
- L494 `TestExecutionRules.test_max_candidates_per_line_enforced(self)`
- L521 `TestExecutionRules.test_candidate_ranking_prefers_cost_2x_then_ir(self)`

## tests/test_phase5_monthly_scores.py

[打开文件](../../tests/test_phase5_monthly_scores.py)

- L15 `class TestPhase5MonthlyScores`
- L18 `TestPhase5MonthlyScores.test_union_contains_monthly_dates(self)`
- L34 `TestPhase5MonthlyScores.test_monthly_scenario_gets_scores(self)`
- L64 `TestPhase5MonthlyScores.test_monthly_n_periods_sufficient(self)`

## tests/test_photoresist_live_data_updater.py

[打开文件](../../tests/test_photoresist_live_data_updater.py)

- L21 `test_month_end_rollover()`
- L25 `test_year_end_rollover()`
- L29 `test_leap_february()`
- L35 `test_weekend_and_holiday_spans_are_plain_calendar_math()`
- L42 `test_integer_plus_one_is_wrong_and_we_do_not_do_it()`
- L51 `test_contiguous_ranges_merges_across_weekends_splits_on_long_gaps()`
- L58 `test_contiguous_ranges_empty()`
- L63 `class FakeCache`
- L66 `FakeCache.__init__(self, dates_by_code)`
- L69 `FakeCache.read(self, table_name, columns=None, filters=None, partition=None)`
- L84 `test_security_update_plan_is_per_code_not_group_max()`
- L100 `test_security_update_plan_empty_cache_fetches_everything()`

## tests/test_photoresist_live_engines.py

[打开文件](../../tests/test_photoresist_live_engines.py)

- L54 `_sev(triggered, ret5, pct, breadth=0.5, amount=1.0, limit_down=0)`
- L62 `test_severity_p0_p1_p2_p3_p4_ladder()`
- L73 `test_p4_breadth_alone_allowed_only_when_confirmation_disabled()`
- L81 `test_severity_never_reclassifies_gate()`
- L88 `test_p4_stress_from_active_members_even_if_gate_excluded_them()`
- L95 `test_active_stress_keeps_denominator_and_ignores_stale_suspension_amount()`
- L118 `_snapshot(rets, codes=None, valid=None)`
- L129 `test_commonality_sector_wide()`
- L137 `test_commonality_mixed()`
- L143 `test_commonality_stock_driven()`
- L152 `test_commonality_insufficient_data()`
- L158 `test_dual_commonality_two_scopes()`
- L175 `test_dual_commonality_insufficient_signal_members()`
- L185 `test_reversal_status_by_regime()`
- L198 `test_reversal_reports_wilson_interval_not_point_probability()`
- L208 `test_wilson_interval_bounds()`
- L216 `test_live_config_matches_frozen_research_gate()`
- L222 `test_frozen_gate_drift_detected()`
- L230 `test_rolling_quantile_uses_shifted_history_only()`

## tests/test_photoresist_live_members.py

[打开文件](../../tests/test_photoresist_live_members.py)

- L34 `_members(codes=CODES)`
- L38 `_panel(n_days=260, codes=CODES, overrides=None)`
- L55 `test_four_active_three_eligible_with_limit_down_reason()`
- L72 `test_eligibility_snapshot_matches_frozen_filter()`
- L103 `test_active_stress_counts_limit_down_excluded_from_gate()`
- L114 `test_active_stress_exact_limit_price_beats_proxy()`
- L128 `test_active_stress_breadth_over_all_active_members()`

## tests/test_photoresist_live_notifications.py

[打开文件](../../tests/test_photoresist_live_notifications.py)

- L19 `test_push_policy_transitions()`
- L37 `_failing_webhook(monkeypatch, results)`
- L48 `test_first_trigger_pushes_exactly_once(tmp_path, monkeypatch)`
- L63 `test_upgrade_key_differs_from_first_trigger_and_pushes_once(tmp_path, monkeypatch)`
- L75 `test_webhook_failure_is_retryable_without_touching_facts(tmp_path, monkeypatch)`
- L90 `test_retry_preserves_full_original_markdown(tmp_path, monkeypatch)`
- L105 `test_state_commit_crash_before_first_attempt_recovers_from_journal(tmp_path, monkeypatch)`
- L141 `test_retry_gives_up_after_max_attempts(tmp_path, monkeypatch)`
- L153 `test_daily_refresh_is_not_a_push(tmp_path, monkeypatch)`
- L165 `test_no_webhook_configured_marks_delivered(tmp_path)`

## tests/test_photoresist_live_outcome_tradability.py

[打开文件](../../tests/test_photoresist_live_outcome_tradability.py)

- L32 `_panel(days, codes=CODES, overrides=None, drop=None)`
- L53 `_signal(date=2, codes=CODES)`
- L58 `_suspends(*keys)`
- L72 `test_entry_resolves_and_freezes_components()`
- L80 `test_outcome_uses_frozen_entry_resolution_after_price_revision()`
- L96 `test_limit_up_on_entry_day_excluded()`
- L104 `test_suspended_on_entry_day_excluded()`
- L110 `test_missing_entry_day_row_excluded()`
- L116 `test_entry_uses_frozen_20d_liquidity_threshold()`
- L144 `test_entry_liquidity_fails_closed_without_minimum_history()`
- L158 `test_fewer_than_three_tradable_is_no_tradable_basket()`
- L172 `test_pending_before_entry_data()`
- L182 `test_suspension_carries_last_close_on_unified_grid()`
- L207 `test_unexplained_partial_gap_blocks_formal_outcome()`
- L225 `test_calendar_alignment_across_members()`
- L243 `test_all_components_unexplained_missing_blocks_outcome()`
- L253 `test_audited_suspension_then_resumption_can_complete()`
- L266 `test_target_and_upper_bound_metrics()`
- L281 `test_same_day_tp_sl_conservative_and_flagged()`
- L294 `test_mae_mfe_from_adjusted_extremes()`

## tests/test_photoresist_live_quality_gate.py

[打开文件](../../tests/test_photoresist_live_quality_gate.py)

- L22 `_config(**overrides)`
- L37 `_days(n=300, end='2025-12-31')`
- L42 `_make_prices(days, codes=CORE, drop=None)`
- L59 `_make_indices(days, codes=INDICES, drop=None)`
- L67 `_gate(prices, indices, days, config=None, suspend=None)`
- L75 `test_normal_when_all_components_current()`
- L84 `test_stale_stock_data_blocks()`
- L94 `test_stock_missing_20_middle_days_blocks_even_with_fresh_max_date()`
- L104 `test_index_missing_100_middle_days_blocks_even_with_fresh_max_date()`
- L114 `test_legal_suspension_gap_does_not_block()`
- L129 `test_unexplained_gap_blocks()`
- L138 `test_missing_open_dates_fails_closed()`
- L148 `test_component_missing_on_eval_day_with_suspension_degrades()`
- L162 `test_fewer_than_three_components_blocks()`
- L174 `test_duplicate_stock_and_index_keys_block()`
- L192 `test_live_raw_loaders_preserve_source_duplicates(tmp_path, monkeypatch)`
- L226 `test_adj_ohlc_missing_any_column_blocks()`
- L236 `test_nonpositive_adj_price_blocks()`
- L245 `test_amount_missing_blocks_when_required()`
- L255 `test_amount_missing_warns_when_config_false()`
- L265 `test_insufficient_warmup_blocks()`

## tests/test_photoresist_live_runner_transactions.py

[打开文件](../../tests/test_photoresist_live_runner_transactions.py)

- L30 `drive(journal: TransitionJournal, state: PanicState, days: list[tuple], run_id: str='run_test', active_max: int=20, cooldown: int=5)`
- L53 `_quiet_days(start_idx: int, n: int)`
- L60 `test_journal_append_is_idempotent(tmp_path)`
- L69 `test_journal_rebuilds_state_registry_history(tmp_path)`
- L92 `test_entry_resolution_is_append_only_and_requires_explicit_revision(tmp_path)`
- L128 `test_corrupt_state_recovered_from_journal(tmp_path)`
- L138 `test_proven_idle_checkpoint_matches_full_trigger_replay(tmp_path)`
- L177 `test_initialization_falls_back_to_full_history_without_idle_proof()`
- L192 `test_catchup_two_events_get_distinct_signal_ids(tmp_path)`
- L211 `test_catchup_ending_idle_registry_keeps_event_ids(tmp_path)`
- L228 `test_catchup_spans_active_cooldown_idle(tmp_path)`
- L243 `test_catchup_p2_to_p4_upgrade_emits_once(tmp_path)`
- L257 `test_historical_transitions_keep_their_own_snapshot(tmp_path)`
- L278 `test_failure_before_state_commit_recovers_without_losing_signal(tmp_path)`
- L315 `test_rerun_after_crash_journal_dedupes(tmp_path)`
- L332 `test_run_lock_blocks_second_instance(tmp_path)`
- L343 `test_stale_lock_taken_over_with_owner_recorded(tmp_path)`

## tests/test_photoresist_live_state_machine.py

[打开文件](../../tests/test_photoresist_live_state_machine.py)

- L18 `advance(state, day, triggered, severity='P2', **kwargs)`
- L24 `test_first_trigger_records_live_signal_date_and_emits()`
- L35 `test_no_new_event_while_active()`
- L47 `test_severity_upgrade_emits_notification()`
- L60 `test_active_window_expires_into_cooldown()`
- L68 `test_cooldown_requires_consecutive_clear_days()`
- L88 `test_cooldown_severity_upgrade_notifies_without_new_event()`
- L114 `test_duplicate_run_is_idempotent()`
- L124 `test_state_persistence_roundtrip(tmp_path)`
- L133 `test_corrupt_state_file_raises(tmp_path)`
- L140 `test_new_event_after_full_cycle_gets_new_signal_id()`

## tests/test_photoresist_live_universe.py

[打开文件](../../tests/test_photoresist_live_universe.py)

- L24 `universe()`
- L29 `test_historical_v1_periods_untouched(universe)`
- L38 `test_2026_periods_are_new_entries_not_overwrites(universe)`
- L48 `test_core_pool_continuous_across_year_boundary(universe)`
- L54 `test_confirmed_desk_research_is_reported_pending_review(universe)`
- L59 `test_membership_expires_after_effective_end(universe)`
- L65 `test_no_overlapping_periods_validated()`
- L83 `test_announcement_date_gates_membership()`

## tests/test_photoresist_loader_date_boundaries.py

[打开文件](../../tests/test_photoresist_loader_date_boundaries.py)

- L9 `test_iter_year_dirs_uses_prior_warmup_but_never_future_year(tmp_path: Path)`
- L18 `test_clip_loaded_dates_keeps_warmup_and_enforces_hard_end()`
- L31 `test_safe_dedup_rejects_missing_vs_present_conflict()`
- L41 `test_builder_promotion_removes_stale_optional_outputs(tmp_path: Path)`
- L62 `test_builder_promotion_rolls_back_on_manifest_failure(tmp_path: Path, monkeypatch)`

## tests/test_photoresist_panic_attribution.py

[打开文件](../../tests/test_photoresist_panic_attribution.py)

- L14 `test_select_non_overlapping_removes_shared_holding_windows()`
- L24 `test_backward_features_are_shifted_before_event_date()`
- L38 `test_summary_reports_semiconductor_excess_and_non_overlap()`

## tests/test_photoresist_panic_events.py

[打开文件](../../tests/test_photoresist_panic_events.py)

- L34 `_make_valid_dates(start_ymd: int, n_days: int)`
- L46 `sample_universe_config()`
- L85 `sample_prices()`
- L119 `sample_gate_config()`
- L131 `class TestPITUniverse`
- L132 `TestPITUniverse.test_stock_not_available_before_effective_start(self, sample_universe_config)`
- L139 `TestPITUniverse.test_stock_available_after_effective_start(self, sample_universe_config)`
- L144 `TestPITUniverse.test_core_does_not_include_adjacent_or_mapping(self, sample_universe_config)`
- L151 `TestPITUniverse.test_adjacent_separate_from_mapping(self, sample_universe_config)`
- L156 `TestPITUniverse.test_low_confidence_excluded_with_medium(self, sample_universe_config)`
- L167 `class TestAmountRatio20d`
- L168 `TestAmountRatio20d.test_not_constant_one(self, sample_prices)`
- L177 `TestAmountRatio20d.test_elevated_during_panic(self, sample_prices)`
- L206 `class TestBasketConstruction`
- L207 `TestBasketConstruction.test_basket_not_empty(self, sample_universe_config, sample_prices)`
- L220 `TestBasketConstruction.test_basket_build_diagnostics_records_skipped_days(self, sample_universe_config, sample_prices)`
- L233 `TestBasketConstruction.test_three_component_cap_enforced_with_cash_residual(self, sample_universe_config, sample_prices)`
- L258 `class TestPanicGateV2`
- L259 `TestPanicGateV2.test_quantile_excludes_current_day(self, sample_universe_config, sample_prices, sample_gate_config)`
- L280 `TestPanicGateV2.test_no_trigger_on_normal_market(self, sample_universe_config, sample_prices, sample_gate_config)`
- L304 `class TestEventClusteringV2`
- L305 `TestEventClusteringV2.test_trading_day_gap_clustering(self)`
- L344 `TestEventClusteringV2.test_yyyymmdd_diff_misleading(self)`
- L354 `TestEventClusteringV2.test_cluster_naming(self)`
- L391 `class TestEligibility`
- L392 `TestEligibility.test_consecutive_limit_down_detection(self, sample_prices)`
- L406 `TestEligibility.test_no_consecutive_limit_down_normal(self, sample_prices)`
- L413 `TestEligibility.test_limit_price_columns_are_not_boolean_flags(self, sample_prices)`
- L433 `TestEligibility.test_suspended_detection_price_missing(self, sample_prices)`
- L440 `TestEligibility.test_not_suspended_when_price_exists(self, sample_prices)`
- L450 `class TestEdgeCases`
- L451 `TestEdgeCases.test_empty_universe(self)`
- L456 `TestEdgeCases.test_date_range_filtering(self, sample_universe_config)`

## tests/test_photoresist_panic_execution.py

[打开文件](../../tests/test_photoresist_panic_execution.py)

- L39 `_make_valid_dates(start_ymd: int, n_days: int)`
- L51 `sample_calendar()`
- L56 `sample_prices()`
- L91 `sample_universe()`
- L103 `sample_events()`
- L113 `sample_core_basket(sample_prices)`
- L124 `class TestLag1CloseExecution`
- L125 `TestLag1CloseExecution.test_exec_date_after_event_date(self, sample_events)`
- L129 `TestLag1CloseExecution.test_close_to_close_trade(self, sample_prices, sample_calendar)`
- L143 `TestLag1CloseExecution.test_forward_return_excludes_event_day_gain(self, sample_events, sample_prices, sample_core_basket, sample_calendar)`
- L154 `class TestMustBeEventStock`
- L155 `TestMustBeEventStock.test_liquidity_core_requires_event_stock(self, sample_prices, sample_universe, sample_calendar)`
- L183 `TestMustBeEventStock.test_strength_and_mid_drop_require_event_stock(self, sample_prices)`
- L208 `TestMustBeEventStock.test_top1_returns_none_when_no_event_stock(self, sample_prices)`
- L226 `class TestPITTop1`
- L227 `TestPITTop1.test_stock_after_effective_start_not_selected(self, sample_prices, sample_calendar)`
- L252 `TestPITTop1.test_min_listing_days_filter(self, sample_prices, sample_universe, sample_calendar)`
- L272 `TestPITTop1.test_mock_stock_status_excludes_st(self, sample_prices, sample_universe, sample_calendar)`
- L301 `class TestLimitHandling`
- L302 `TestLimitHandling.test_limit_up_no_buy(self, sample_prices, sample_calendar)`
- L309 `TestLimitHandling.test_limit_down_entry_rejected(self, sample_prices, sample_calendar)`
- L337 `class TestBasketDiagnostics`
- L338 `TestBasketDiagnostics.test_basket_loo_identifies_single_stock_dominance(self)`
- L376 `TestBasketDiagnostics.test_basket_contribution_output_structure(self)`
- L399 `class TestGoNoGoV2`
- L400 `TestGoNoGoV2.test_both_invalid_empty(self)`
- L405 `TestGoNoGoV2.test_basket_valid_top1_invalid(self)`
- L421 `TestGoNoGoV2.test_both_valid(self)`
- L440 `TestGoNoGoV2.test_basket_loo_failure_blocks_event_go(self)`
- L465 `TestGoNoGoV2.test_50bps_cost_reversal(self)`
- L487 `TestGoNoGoV2.test_not_implemented_features_skipped(self)`
- L509 `class TestConfigConsistency`
- L510 `TestConfigConsistency.test_implemented_rules_in_output(self)`
- L519 `TestConfigConsistency.test_not_implemented_in_manifest(self)`
- L526 `TestConfigConsistency.test_disabled_features_explicit_in_config(self)`
- L537 `TestConfigConsistency.test_report_feature_status_lists_implemented_and_not_implemented(self, tmp_path)`
- L558 `class TestEdgeCases`
- L559 `TestEdgeCases.test_empty_events(self, sample_prices, sample_universe, sample_core_basket, sample_calendar)`
- L564 `TestEdgeCases.test_no_core_stocks(self, sample_events, sample_prices, sample_core_basket, sample_calendar)`
- L571 `TestEdgeCases.test_empty_diagnostics(self)`

## tests/test_photoresist_panic_monitor.py

[打开文件](../../tests/test_photoresist_panic_monitor.py)

- L20 `test_small_absolute_drop_can_be_relative_panic()`
- L24 `test_absolute_panic_levels_are_ordered()`
- L30 `test_non_trigger_is_watch_not_panic()`
- L34 `test_staleness_is_explicit()`
- L39 `test_frozen_input_contract_returns_universe_second(tmp_path)`
- L55 `test_repository_data_package_is_importable_from_monitor()`

## tests/test_photoresist_panic_path_rules.py

[打开文件](../../tests/test_photoresist_panic_path_rules.py)

- L66 `_make_calendar(start_ymd: int=20200102, n_days: int=200)`
- L78 `_make_basket_rets(daily_rets: list[float])`
- L88 `_make_dates(calendar: np.ndarray, entry_date: int, n_days: int)`
- L93 `_make_semi_lookup(dates: np.ndarray)`
- L107 `class TestFirstTriggerDetection`
- L108 `TestFirstTriggerDetection.test_uses_online_first_trigger_per_cluster(self)`
- L116 `TestFirstTriggerDetection.test_string_flags_and_missing_column_are_safe(self)`
- L129 `class TestPathParser`
- L132 `TestPathParser.test_sustained_repair(self)`
- L165 `TestPathParser.test_no_bounce(self)`
- L188 `TestPathParser.test_failed_bounce(self)`
- L221 `TestPathParser.test_w_recovery(self)`
- L253 `TestPathParser.test_undercut_diagnostic(self)`
- L282 `TestPathParser.test__classify_path_type(self)`
- L324 `class TestRuleSimulator`
- L328 `TestRuleSimulator.calendar(self)`
- L332 `TestRuleSimulator.entry_date(self, calendar)`
- L336 `TestRuleSimulator.rising_rets(self)`
- L342 `TestRuleSimulator.rising_dates(self, calendar, entry_date)`
- L346 `TestRuleSimulator.path_with_breakout(self, calendar)`
- L361 `TestRuleSimulator.path_no_breakout(self, calendar)`
- L375 `TestRuleSimulator.test_r0_basic(self, calendar, entry_date, rising_rets, rising_dates)`
- L391 `TestRuleSimulator.test_r0_stop_loss(self, calendar, entry_date)`
- L405 `TestRuleSimulator.test_r1_no_confirmation_returns_no_trade(self, calendar, entry_date, rising_rets, rising_dates, path_no_breakout)`
- L417 `TestRuleSimulator.test_r1_with_confirmation(self, calendar, entry_date, rising_rets, rising_dates, path_with_breakout)`
- L430 `TestRuleSimulator.test_r2_staged_both_legs(self, calendar, entry_date, rising_rets, rising_dates, path_with_breakout)`
- L443 `TestRuleSimulator.test_r2_single_leg_no_breakout(self, calendar, entry_date, rising_rets, rising_dates, path_no_breakout)`
- L454 `TestRuleSimulator.test_r3_stop_no_reentry(self, calendar, entry_date, path_no_breakout)`
- L468 `TestRuleSimulator.test_r3_stop_with_reentry(self, calendar, entry_date, path_with_breakout)`
- L486 `TestRuleSimulator.test_confirmation_lag(self, calendar, entry_date, rising_rets, rising_dates, path_with_breakout)`
- L502 `class TestStatistics`
- L505 `TestStatistics.test_paired_differences_with_no_trade(self)`
- L543 `TestStatistics.test_bootstrap_ci(self)`
- L550 `TestStatistics.test_bootstrap_ci_small_sample(self)`
- L556 `TestStatistics.test__flatten_trade(self)`
- L582 `class TestEdgeCases`
- L585 `TestEdgeCases.test_right_censored_path(self)`
- L609 `TestEdgeCases.test_nan_nav_handling(self)`
- L638 `TestEdgeCases.test_event_overlap_truncation(self)`
- L669 `class TestCostAccounting`
- L672 `TestCostAccounting.test_round_trip_cost_helper(self)`
- L683 `TestCostAccounting.test_r0_cost_is_one_percent_at_100bp(self)`
- L700 `TestCostAccounting.test_r2_two_halves_cost_is_one_percent(self)`
- L729 `TestCostAccounting.test_r2_single_half_cost_is_half_percent(self)`
- L754 `TestCostAccounting.test_r3_double_round_trip_cost_is_two_percent(self)`
- L783 `TestCostAccounting.test_cost_scenarios_all_correct(self)`
- L800 `class TestStopExecution`
- L803 `TestStopExecution.test_stop_entry_is_day_k_plus_1(self)`
- L831 `TestStopExecution.test_stop_without_k_plus_1_falls_through_to_boundary_exit(self)`
- L866 `TestStopExecution.test_stop_uses_position_return_not_event_return(self)`
- L883 `TestStopExecution.test_r1_stop_relative_to_r1_entry(self)`
- L924 `class TestExecutionContext`
- L925 `TestExecutionContext.test_limit_down_blocks_basket_sell(self)`
- L947 `TestExecutionContext.test_r1_limit_up_entry_is_untradable_not_zero_return(self)`
- L987 `class TestSignalAnchors`
- L990 `TestSignalAnchors.test_compute_signal_anchors_basic(self)`
- L1011 `TestSignalAnchors.test_missing_adj_low_does_not_fallback_to_signal_close(self)`
- L1023 `TestSignalAnchors.test_signal_anchor_docstring_contract(self)`
- L1032 `class TestTruncationClassification`
- L1035 `TestTruncationClassification.test_truncated_below_20d_is_right_censored(self)`
- L1063 `TestTruncationClassification.test_entry_plus_19_future_sessions_is_still_censored(self)`
- L1078 `TestTruncationClassification.test_unexplained_gap_excludes_path_classification(self)`
- L1094 `TestTruncationClassification.test_truncated_but_20d_available_classified_normally(self)`
- L1121 `TestTruncationClassification.test__classify_path_type_insufficient_data(self)`
- L1130 `TestTruncationClassification.test__classify_path_type_no_bounce(self)`
- L1139 `class TestEntryResolution`
- L1141 `TestEntryResolution._prices(codes=('A.SH', 'B.SH', 'C.SH', 'D.SH'))`
- L1153 `TestEntryResolution.test_non_st_rows_survive_and_thousand_cny_threshold_is_normalized(self)`
- L1170 `TestEntryResolution.test_exact_limit_price_overrides_10pct_proxy_for_20pct_board(self)`
- L1185 `TestEntryResolution.test_audited_entry_suspension_is_excluded(self)`
- L1199 `TestEntryResolution.test_construct_events_end_to_end_uses_first_trigger_and_resolved_basket(self)`
- L1239 `class TestFrozenBasket`
- L1242 `TestFrozenBasket.test_build_frozen_basket_path_requires_min_components(self)`
- L1250 `TestFrozenBasket.test_frozen_basket_rejects_missing_entry_stock(self)`
- L1264 `TestFrozenBasket.test_unexplained_missing_propagates_nan_with_frozen_denominator(self)`
- L1284 `TestFrozenBasket.test_audited_suspension_carries_without_changing_denominator(self)`
- L1303 `TestFrozenBasket.test_n_entry_components_is_resolved_count(self)`
- L1316 `class TestSemiNavAlignment`
- L1319 `TestSemiNavAlignment.test_semi_nav_reflects_same_day_close(self)`
- L1331 `TestSemiNavAlignment.test_excess_return_is_cost_adjusted(self)`
- L1343 `TestSemiNavAlignment.test_target_hit_survives_fade_before_day_20(self)`
- L1355 `class TestManifest`
- L1358 `TestManifest.test_event_record_has_frozen_codes(self)`
- L1371 `TestManifest.test_event_record_exclusion_tracking(self)`
- L1387 `TestManifest.test_manifest_contains_real_input_digests_and_path_failures(self)`
- L1416 `TestManifest.test_dataframe_digest_is_row_order_independent(self)`
- L1423 `class TestPositionReturn`
- L1426 `TestPositionReturn.test_entry_at_original_entry(self)`
- L1431 `TestPositionReturn.test_entry_after_gain(self)`
- L1438 `TestPositionReturn.test_entry_after_loss(self)`
- L1445 `TestPositionReturn.test_r1_position_return_applied(self)`
- L1481 `class TestReportCoverage`
- L1484 `TestReportCoverage.test_cost_sensitivity_excludes_censored_and_rejected(self)`
- L1512 `TestReportCoverage.test_report_generation_handles_right_censored_path_type(self)`
- L1540 `TestReportCoverage.test_empty_ledgers_produce_auditable_report_without_crashing(self)`

## tests/test_photoresist_portfolio_shadow.py

[打开文件](../../tests/test_photoresist_portfolio_shadow.py)

- L21 `_trade(signal_id: str, rule_id: str, net_return: float, legs: list[tuple[str, int, float]])`
- L42 `_shadow_args(**overrides)`
- L60 `test_portfolio_curve_uses_real_daily_drawdown_not_smoothed_endpoint()`
- L79 `test_r2_add_leg_is_not_mistaken_for_the_exit()`
- L102 `test_half_position_10pct_move_gives_5pct_not_2_5pct()`
- L120 `test_two_concurrent_half_positions_equal_capital_allocation()`
- L147 `test_full_period_end_extends_curve_with_cash_tail()`
- L173 `test_portfolio_exposure_includes_cash_gaps()`
- L190 `test_shadow_contract_rejects_parameter_or_source_drift()`
- L204 `test_shadow_contract_forward_start_is_after_freeze()`
- L218 `test_shadow_outcomes_are_forward_only_idempotent_and_append_only(monkeypatch)`
- L256 `test_pending_right_censored_outcome_can_mature_to_realized(tmp_path: Path)`
- L299 `test_shadow_outcomes_are_idempotent_after_csv_float_roundtrip(tmp_path: Path)`

## tests/test_photoresist_shadow_gates.py

[打开文件](../../tests/test_photoresist_shadow_gates.py)

- L21 `_contract()`
- L28 `_forward_outcomes(n: int=15)`
- L52 `_portfolio_metrics()`
- L59 `test_frozen_gate_contract_hash_is_valid_and_tamper_evident()`
- L68 `test_gate_contract_must_be_json_object()`
- L73 `test_immature_forward_sample_waits_without_testing_substantive_gates()`
- L83 `test_mature_two_year_sample_is_capped_below_manual_review()`
- L102 `test_three_year_sample_with_cluster_bootstrap_can_reach_manual_review()`
- L142 `test_any_substantive_failure_keeps_strategy_research_only()`
- L156 `test_historical_event_is_rejected_before_gate_evaluation()`
- L163 `test_stale_or_incomplete_forward_data_fail_integrity()`
- L195 `test_current_complete_forward_data_pass_freshness()`
- L224 `_freshness_v2(**overrides)`
- L257 `test_freshness_per_code_all_fresh_passes()`
- L261 `test_freshness_per_code_stale_price_fails()`
- L274 `test_freshness_per_code_missing_price_fails()`
- L284 `test_freshness_per_code_stale_basket_constituent_fails()`
- L295 `test_freshness_without_per_code_schema_fails_closed()`
- L305 `test_gate_does_not_freeze_dynamic_shadow_files(tmp_path, monkeypatch)`
- L342 `test_nav_missing_expected_rule_column_fails_closed(tmp_path, monkeypatch)`

## tests/test_photoresist_take_profit.py

[打开文件](../../tests/test_photoresist_take_profit.py)

- L15 `test_online_signal_uses_first_trigger_and_cooldown()`
- L24 `test_take_profit_starts_after_entry_and_uses_adjusted_high()`
- L35 `test_net_five_percent_target_includes_round_trip_cost()`
- L44 `test_wilson_interval_contains_observed_rate()`

## tests/test_photoresist_threshold_validation.py

[打开文件](../../tests/test_photoresist_threshold_validation.py)

- L25 `_dates(start: str, periods: int)`
- L32 `_gate_config(**overrides)`
- L45 `test_rolling_quantile_excludes_current_day()`
- L58 `test_all_configured_gates_can_be_built_without_best_gate_selection()`
- L78 `test_event_clustering_uses_trading_day_positions()`
- L96 `test_market_regime_does_not_change_when_future_prices_change()`
- L113 `test_placebo_excludes_event_buffer_and_matches_year_and_regime()`
- L143 `test_bootstrap_returns_reproducible_confidence_interval()`
- L161 `test_acceptance_rejects_significance_and_match_coverage_failures()`
- L194 `test_report_contains_all_gates_and_acceptance_result()`

## tests/test_photoresist_upstream_manifest_integrity.py

[打开文件](../../tests/test_photoresist_upstream_manifest_integrity.py)

- L15 `_write_manifest(tmp_path)`
- L41 `test_matching_builder_outputs_are_accepted(tmp_path)`
- L47 `test_mixed_or_stale_builder_csv_is_rejected(tmp_path)`
- L57 `test_legacy_manifest_without_output_inventory_is_rejected(tmp_path)`

## tests/test_pit_product_universe.py

[打开文件](../../tests/test_pit_product_universe.py)

- L15 `_scratch()`
- L25 `class _Cal`
- L29 `_Cal.load(self, **kwargs)`
- L32 `_Cal.next_trade_day(self, date, n=1)`
- L40 `test_pit_asof_skips_unavailable_same_day_snapshot()`
- L46 `test_build_available_constituents_lag1(monkeypatch)`
- L56 `test_local_universe_fn_does_not_use_same_day_snapshot(monkeypatch)`
- L74 `test_attach_adj_open_matches_fill_scale()`
- L90 `test_board_all_keeps_chinext_and_star()`
- L99 `test_refuse_existing_run_dir()`
- L114 `test_input_lock_lists_prices_and_limits()`
- L129 `test_freeze_manifest_hashes_outputs()`
- L154 `test_weights_doc_path_is_relative()`

## tests/test_prepare_sector_panic_data.py

[打开文件](../../tests/test_prepare_sector_panic_data.py)

- L13 `test_completed_month_end_uses_previous_month_for_partial_month()`
- L17 `test_completed_month_end_keeps_natural_month_end()`
- L21 `test_month_ends_are_calendar_correct_across_year_boundary()`
- L30 `test_missing_evidence_rejects_incomplete_manual_member()`
- L48 `test_complete_evidence_has_no_missing_fields()`
- L61 `test_research_contracts_follow_active_five_sector_scope()`
- L87 `test_manifest_proves_open_only_trade_calendar(tmp_path)`
- L110 `test_trade_calendar_caches_natural_days_but_returns_open_days(tmp_path)`

## tests/test_price_interior_gaps.py

[打开文件](../../tests/test_price_interior_gaps.py)

- L4 `test_interior_hole_between_cached_ends()`
- L11 `test_suspend_day_is_not_a_hole()`
- L18 `test_empty_have()`

## tests/test_price_quality_validation.py

[打开文件](../../tests/test_price_quality_validation.py)

- L10 `class TestPriceQualityValidation`
- L13 `TestPriceQualityValidation.test_normal_data_passes(self)`
- L31 `TestPriceQualityValidation.test_adj_factor_missing_ratio_detected(self)`
- L45 `TestPriceQualityValidation.test_duplicate_rows_detected(self)`
- L57 `TestPriceQualityValidation.test_extreme_daily_return_detected(self)`
- L70 `TestPriceQualityValidation.test_extreme_weekly_return_detected(self)`
- L87 `TestPriceQualityValidation.test_adj_close_raw_close_ratio(self)`
- L107 `TestPriceQualityValidation.test_monthly_summary_produced(self)`

## tests/test_products_metrics.py

[打开文件](../../tests/test_products_metrics.py)

- L16 `test_weekly_rebalance_stride()`
- L22 `test_summarize_go_when_median_excess_non_negative()`
- L32 `test_summarize_nogo_when_median_excess_negative()`

## tests/test_regime_allocator.py

[打开文件](../../tests/test_regime_allocator.py)

- L33 `_default_allocator_config()`
- L65 `_make_regime_probs(dates: list, probs_list: list=None)`
- L98 `class TestRegimeAllocator`
- L101 `TestRegimeAllocator.test_weights_sum_to_one(self)`
- L114 `TestRegimeAllocator.test_weight_cap_enforced(self)`
- L131 `TestRegimeAllocator.test_weight_floor_enforced(self)`
- L149 `TestRegimeAllocator.test_missing_sleeve_renormalized(self)`
- L171 `TestRegimeAllocator.test_min_sleeves_constraint(self)`
- L187 `TestRegimeAllocator.test_all_sleeves_missing_returns_empty(self)`
- L196 `TestRegimeAllocator.test_smoothing_limits_weekly_change(self)`
- L224 `TestRegimeAllocator.test_output_has_all_sleeve_columns(self)`
- L236 `TestRegimeAllocator.test_empty_probs_returns_empty(self)`
- L242 `TestRegimeAllocator.test_mapping_matrix_rows_sum_to_one(self)`
- L249 `TestRegimeAllocator.test_extreme_inputs_dont_crash(self)`
- L264 `TestRegimeAllocator.test_all_sleeves_available_by_default(self)`
- L289 `TestRegimeAllocator.test_sleeve_multipliers_adjust_weights_before_constraints(self)`
- L325 `class TestMappingMatrix`
- L328 `TestMappingMatrix.test_empty_config_produces_equal_weights(self)`
- L348 `TestMappingMatrix.test_partial_config_fills_zeros(self)`
- L368 `class TestShockReversalAllocator`
- L371 `TestShockReversalAllocator.test_shock_reversal_in_sleeve_names(self)`
- L376 `TestShockReversalAllocator.test_shock_reversal_weight_column(self)`
- L388 `TestShockReversalAllocator.test_range_bound_highest_shock_weight(self)`
- L431 `TestShockReversalAllocator.test_shock_unavailable_redistributes(self)`

## tests/test_regime_candidate_config.py

[打开文件](../../tests/test_regime_candidate_config.py)

- L19 `_load_yaml(path: str)`
- L28 `test_candidate_v1_factors_pool_consistent()`
- L41 `test_candidate_v2_factors_pool_consistent()`
- L55 `test_candidate_v3_factors_pool_consistent()`
- L73 `test_candidate_v2_expected_factor_list()`
- L102 `test_candidate_v2_no_disabled_factors_in_sleeves()`

## tests/test_regime_candidate_v4_config.py

[打开文件](../../tests/test_regime_candidate_v4_config.py)

- L15 `_load_config()`
- L22 `_load_candidate_factors()`
- L34 `class TestSleeveStructure`
- L37 `TestSleeveStructure.test_all_sleeves_have_min_two_factors(self)`
- L46 `TestSleeveStructure.test_sleeves_contain_valid_factors(self)`
- L61 `TestSleeveStructure.test_sleeve_names_are_meaningful(self)`
- L71 `class TestRegimeMapping`
- L74 `TestRegimeMapping.test_all_regimes_present(self)`
- L81 `TestRegimeMapping.test_regime_weights_sum_close_to_one(self)`
- L93 `TestRegimeMapping.test_regime_weights_only_reference_valid_sleeves(self)`
- L105 `TestRegimeMapping.test_regime_weights_within_caps(self)`
- L127 `class TestPerformanceOverlay`
- L130 `TestPerformanceOverlay.test_overlay_disabled_by_default(self)`
- L138 `class TestAllocatorConfig`
- L141 `TestAllocatorConfig.test_min_sleeves_reasonable(self)`
- L146 `TestAllocatorConfig.test_min_active_factors_reasonable(self)`
- L153 `class TestConfigIntegrity`
- L156 `TestConfigIntegrity.test_regime_detector_has_required_fields(self)`
- L163 `TestConfigIntegrity.test_factor_alignment_has_all_fundamental_factors(self)`
- L172 `TestConfigIntegrity.test_no_duplicate_factors_across_sleeves(self)`

## tests/test_regime_candidate_v4_r2_config.py

[打开文件](../../tests/test_regime_candidate_v4_r2_config.py)

- L27 `class TestRegimeConfig`
- L31 `TestRegimeConfig.regime_cfg(self)`
- L37 `TestRegimeConfig.factors_cfg(self)`
- L42 `TestRegimeConfig.test_config_is_valid_yaml(self, regime_cfg)`
- L48 `TestRegimeConfig.test_enabled(self, regime_cfg)`
- L52 `TestRegimeConfig.test_sleeve_factors_in_candidate_pool(self, regime_cfg, factors_cfg)`
- L76 `TestRegimeConfig.test_no_fail_factors_in_sleeves(self, regime_cfg, factors_cfg)`
- L98 `TestRegimeConfig.test_allocator_weights_sum_to_1_or_all_zero(self, regime_cfg)`
- L121 `TestRegimeConfig.test_allocator_weight_bounds(self, regime_cfg)`
- L132 `TestRegimeConfig.test_performance_overlay_disabled(self, regime_cfg)`
- L139 `TestRegimeConfig.test_min_sleeves_valid(self, regime_cfg)`
- L151 `TestRegimeConfig.test_empty_sleeves_documented(self, regime_cfg)`
- L162 `TestRegimeConfig.test_regime_detector_config(self, regime_cfg)`
- L169 `TestRegimeConfig.test_sleeve_composite_config(self, regime_cfg)`
- L176 `TestRegimeConfig.test_fundamental_factors_consistent(self, regime_cfg, factors_cfg)`

## tests/test_regime_composite.py

[打开文件](../../tests/test_regime_composite.py)

- L31 `_make_sleeve_score(sleeve_name: str, dates: list, n_stocks: int=30, score_mean: float=0.0, score_std: float=1.0, rng_seed: int=42)`
- L52 `_make_sleeve_weights(dates: list, weights_dict: dict=None)`
- L78 `class TestRegimeCompositeBuilder`
- L81 `TestRegimeCompositeBuilder.test_output_has_required_columns(self)`
- L99 `TestRegimeCompositeBuilder.test_score_is_zscored_cross_sectionally(self)`
- L120 `TestRegimeCompositeBuilder.test_two_sleeves_combine_correctly(self)`
- L161 `TestRegimeCompositeBuilder.test_single_sleeve_returns_empty(self)`
- L177 `TestRegimeCompositeBuilder.test_missing_sleeve_skipped(self)`
- L196 `TestRegimeCompositeBuilder.test_weight_zero_sleeve_skipped(self)`
- L216 `TestRegimeCompositeBuilder.test_empty_weights_returns_empty(self)`
- L223 `TestRegimeCompositeBuilder.test_multiple_dates_produces_all_rows(self)`
- L242 `TestRegimeCompositeBuilder.test_different_stocks_per_sleeve_handled(self)`

## tests/test_regime_config_validation.py

[打开文件](../../tests/test_regime_config_validation.py)

- L25 `sleeve_config()`
- L34 `class TestConfigValidation`
- L37 `TestConfigValidation.test_hard_cap_true_warns_on_small_sleeves(self, sleeve_config, caplog)`
- L53 `TestConfigValidation.test_default_config_no_hard_cap_warnings(self, sleeve_config, caplog)`
- L72 `TestConfigValidation.test_min_active_factors_exceeds_factor_count(self, sleeve_config, caplog)`
- L90 `TestConfigValidation.test_empty_sleeve_detected(self, caplog)`

## tests/test_regime_detector.py

[打开文件](../../tests/test_regime_detector.py)

- L34 `_make_index_df(n_days: int=250, trend: float=0.0, volatility: float=0.015, start_price: float=100.0, start_date: int=20200101, rng_seed: int=42)`
- L66 `_generate_sequential_dates(start: int, n: int)`
- L84 `_make_prices_df(n_stocks: int=200, n_days: int=250, trend: float=0.0, volatility: float=0.02, start_date: int=20200101, rng_seed: int=42)`
- L114 `_default_detector_config()`
- L129 `class TestRegimeDetector`
- L132 `TestRegimeDetector.test_compute_features_basic_shape(self)`
- L148 `TestRegimeDetector.test_trend_up_detected_for_monotonic_rise(self)`
- L169 `TestRegimeDetector.test_trend_down_detected_for_decline(self)`
- L186 `TestRegimeDetector.test_high_vol_detected_for_large_swings(self)`
- L212 `TestRegimeDetector.test_range_bound_gets_reasonable_prob(self)`
- L225 `TestRegimeDetector.test_predict_regime_probs_sums_to_one(self)`
- L240 `TestRegimeDetector.test_empty_index_returns_empty(self)`
- L251 `TestRegimeDetector.test_insufficient_history_skipped(self)`
- L265 `TestRegimeDetector.test_very_short_history_skipped(self)`
- L274 `TestRegimeDetector.test_smoothing_reduces_noise(self)`
- L299 `TestRegimeDetector.test_compute_features_with_prices_breadth(self)`
- L314 `TestRegimeDetector.test_breadth_neutral_without_prices(self)`
- L328 `TestRegimeDetector.test_trend_strength_sign_matches_market(self)`
- L345 `class TestLoadRegimeConfig`
- L348 `TestLoadRegimeConfig.test_loads_default_config(self)`
- L358 `TestLoadRegimeConfig.test_missing_file_raises(self)`

## tests/test_regime_detector_v2.py

[打开文件](../../tests/test_regime_detector_v2.py)

- L32 `_generate_sequential_dates(start: int, n: int)`
- L48 `_make_index_df(n_days: int=500, trend: float=0.0, volatility: float=0.015, start_price: float=100.0, start_date: int=20200101, rng_seed: int=42)`
- L71 `_v1_config()`
- L82 `_v2_config()`
- L106 `class TestRegimeDetectorV2`
- L109 `TestRegimeDetectorV2.test_v2_probabilities_sum_to_one(self)`
- L129 `TestRegimeDetectorV2.test_v2_range_bound_lower_than_v1(self)`
- L151 `TestRegimeDetectorV2.test_v2_normalization_stabilizes_features(self)`
- L168 `TestRegimeDetectorV2.test_v2_insufficient_warmup_graceful(self)`
- L189 `TestRegimeDetectorV2.test_v2_value_rotation_constant_when_disabled(self)`
- L207 `TestRegimeDetectorV2.test_v2_output_compatible_with_v1_allocator(self)`
- L241 `TestRegimeDetectorV2.test_v1_unchanged_no_scoring_version(self)`
- L260 `TestRegimeDetectorV2.test_v2_with_flat_market(self)`
- L277 `TestRegimeDetectorV2.test_v2_strong_trend_detected(self)`
- L297 `TestRegimeDetectorV2.test_v2_high_vol_detected(self)`
- L312 `TestRegimeDetectorV2.test_v2_positive_trend_not_trend_down(self)`
- L330 `TestRegimeDetectorV2.test_v2_neutral_breadth_no_tilt(self)`
- L345 `TestRegimeDetectorV2.test_v2_scoring_temperature_priority(self)`
- L357 `TestRegimeDetectorV2.test_v2_temperature_top_level_fallback(self)`
- L368 `TestRegimeDetectorV2.test_v2_temperature_default(self)`
- L379 `class TestRunIdUniqueness`
- L382 `TestRunIdUniqueness.test_concurrent_ids_are_unique(self)`
- L399 `TestRunIdUniqueness.test_different_configs_have_different_stems(self)`
- L425 `class TestValueRotationRobustness`
- L428 `TestValueRotationRobustness.test_zero_close_falls_back_to_zero(self)`
- L454 `TestValueRotationRobustness.test_nan_inf_close_falls_back_safely(self)`

## tests/test_regime_factor_universe.py

[打开文件](../../tests/test_regime_factor_universe.py)

- L21 `class TestRegimeFactorPool`
- L24 `TestRegimeFactorPool.test_regime_factors_from_sleeves_union(self)`
- L50 `TestRegimeFactorPool.test_regime_missing_factors_logged(self)`
- L75 `TestRegimeFactorPool.test_regime_ignores_factors_yaml_whitelist(self)`

## tests/test_regime_no_leakage.py

[打开文件](../../tests/test_regime_no_leakage.py)

- L31 `_make_index_df(n_days: int=300, trend: float=0.0003, volatility: float=0.015, start_date: int=20200101, rng_seed: int=42)`
- L62 `_detector_config()`
- L76 `class TestRegimeNoLeakage`
- L79 `TestRegimeNoLeakage.test_future_index_data_does_not_affect_regime_probs(self)`
- L114 `TestRegimeNoLeakage.test_future_prices_do_not_affect_breadth(self)`
- L155 `TestRegimeNoLeakage.test_regime_features_only_use_pit_index_data(self)`
- L178 `class TestRegimeAllocatorNoLeakage`
- L181 `TestRegimeAllocatorNoLeakage.test_allocator_is_date_independent(self)`
- L229 `class TestCompositeNoLeakage`
- L232 `TestCompositeNoLeakage.test_composite_only_uses_given_scores(self)`

## tests/test_regime_predictiveness_eval.py

[打开文件](../../tests/test_regime_predictiveness_eval.py)

- L15 `_write_run(root: Path, run_name: str, rows: list[dict])`
- L32 `test_discover_run_artifacts_selects_annual_runs(tmp_path)`
- L77 `test_compute_outputs_has_core_metrics(tmp_path)`

## tests/test_regime_realistic_alignment_gate.py

[打开文件](../../tests/test_regime_realistic_alignment_gate.py)

- L32 `_make_categorical_ts_codes(n_stocks: int, with_unused: bool=True)`
- L42 `_make_monthly_factor(factor_name: str, stocks: list, monthly_dates: list, rng_seed: int=42, use_categorical: bool=True)`
- L68 `_make_weekly_factor(factor_name: str, stocks: list, weekly_dates: list, rng_seed: int=99)`
- L87 `_make_fwd_returns(stocks: list, dates: list, horizon: int=5, rng_seed: int=7)`
- L106 `_generate_weekly_dates(start: int, n_weeks: int)`
- L120 `_generate_monthly_dates(start: int, n_months: int)`
- L138 `class TestCategoricalAlignment`
- L141 `TestCategoricalAlignment.test_categorical_with_unused_categories_aligns(self)`
- L166 `TestCategoricalAlignment.test_categorical_value_sleeve_works(self)`
- L191 `TestCategoricalAlignment.test_future_value_not_leaking_with_categorical(self)`
- L229 `class TestCoverageGateWithSignalFrequency`
- L232 `TestCoverageGateWithSignalFrequency.test_weekly_aligned_passes_coverage_gate(self)`
- L273 `TestCoverageGateWithSignalFrequency.test_legacy_no_expected_dates_fails_on_weekly(self)`
- L311 `TestCoverageGateWithSignalFrequency.test_future_signal_date_not_affecting_gate(self)`
- L360 `class TestValueSleeveIntegration`
- L363 `TestValueSleeveIntegration.test_value_sleeve_composite_nonempty(self)`

## tests/test_regime_warmup_oos.py

[打开文件](../../tests/test_regime_warmup_oos.py)

- L23 `class TestRegimeLoadWindow`
- L26 `TestRegimeLoadWindow.test_load_window_includes_warmup(self)`
- L48 `TestRegimeLoadWindow.test_longer_window_for_long_ma(self)`
- L75 `TestRegimeLoadWindow.test_oos_end_preserved(self)`
- L92 `class TestRegimeDetectorWarmup`
- L95 `TestRegimeDetectorWarmup.test_truncated_data_produces_features(self)`
- L160 `TestRegimeDetectorWarmup.test_early_dates_without_warmup_skipped(self)`
- L201 `class TestBuildRegimeCompositeOOS`
- L204 `TestBuildRegimeCompositeOOS.test_oos_dates_in_regime_probs(self)`
- L329 `class TestWarmupSignalDates`
- L332 `TestWarmupSignalDates.test_build_scoring_signal_dates_union(self)`
- L371 `TestWarmupSignalDates.test_scoring_dates_in_diagnostics(self)`

## tests/test_repair_adj_factor.py

[打开文件](../../tests/test_repair_adj_factor.py)

- L26 `class TestNormalizeSchema`
- L29 `TestNormalizeSchema.test_normalize_basic_types(self)`
- L41 `TestNormalizeSchema.test_drop_nulls_in_keys(self)`
- L52 `TestNormalizeSchema.test_numeric_trade_date_coerced(self)`
- L64 `class TestFindDuplicates`
- L67 `TestFindDuplicates.setup_method(self)`
- L70 `TestFindDuplicates.teardown_method(self)`
- L75 `TestFindDuplicates._write_parquet(self, name, data)`
- L87 `TestFindDuplicates.test_no_duplicates(self)`
- L99 `TestFindDuplicates.test_duplicates_same_value(self)`
- L112 `TestFindDuplicates.test_duplicates_different_value_conflict(self)`
- L127 `TestFindDuplicates.test_duplicates_across_multiple_files(self)`
- L144 `TestFindDuplicates.test_small_numeric_difference_not_conflict(self)`
- L155 `class TestScanPartitionFiles`
- L158 `TestScanPartitionFiles.setup_method(self)`
- L161 `TestScanPartitionFiles.teardown_method(self)`
- L166 `TestScanPartitionFiles.test_empty_partition(self)`
- L171 `TestScanPartitionFiles.test_reads_all_parquet_files(self)`
- L184 `TestScanPartitionFiles.test_skips_bad_files(self)`
- L198 `class TestADJFactorSchema`
- L201 `TestADJFactorSchema.test_schema_fields(self)`
- L210 `class TestDedupPartition`
- L213 `TestDedupPartition.setup_method(self)`
- L219 `TestDedupPartition.teardown_method(self)`
- L224 `TestDedupPartition._write_test_data(self, data_dict)`
- L232 `TestDedupPartition.test_dry_run_no_modification(self)`
- L245 `TestDedupPartition.test_conflict_refuses_to_fix(self)`
- L256 `TestDedupPartition.test_years_filter_respected(self)`

## tests/test_return_attribution.py

[打开文件](../../tests/test_return_attribution.py)

- L25 `test_brinson_adds_up_and_separates_allocation()`
- L39 `test_industry_panel_returns_weight_average()`
- L48 `test_lagged_beta_is_shifted_and_residual_zero_when_beta_one()`
- L60 `test_neutralize_removes_industry_mean()`
- L71 `test_official_weight_coverage_and_integrity_fail_closed()`
- L82 `test_rank_ic_perfect_monotonic()`

## tests/test_robustness_go_nogo.py

[打开文件](../../tests/test_robustness_go_nogo.py)

- L7 `test_go_nogo_checks_recent_oos_optimizer_fallback()`
- L42 `test_warning_check_does_not_force_no_go()`
- L79 `test_unknown_fallback_rate_remains_hard_no_go()`
- L114 `test_all_checks_have_severity()`
- L140 `test_hard_checks_separated_from_warnings()`
- L172 `test_nan_guard_causes_no_go()`

## tests/test_score_to_mu_no_leakage.py

[打开文件](../../tests/test_score_to_mu_no_leakage.py)

- L11 `class TestScoreToMuNoLeakage`
- L14 `TestScoreToMuNoLeakage.test_first_date_mu_is_zero(self)`
- L40 `TestScoreToMuNoLeakage.test_changing_future_return_does_not_change_current_mu(self)`
- L90 `TestScoreToMuNoLeakage.test_t_minus_1_unmatured_forward_return_does_not_change_t_mu(self)`
- L148 `TestScoreToMuNoLeakage.test_matured_forward_return_can_affect_later_mu(self)`
- L210 `TestScoreToMuNoLeakage.test_historical_regression_uses_matured_cutoff(self)`
- L241 `_is_valid_ymd(d: int)`

## tests/test_sector_panic_backtest.py

[打开文件](../../tests/test_sector_panic_backtest.py)

- L23 `test_partial_limit_coverage_is_marked_as_proxy()`
- L36 `test_runtime_limit_gaps_are_scoped_to_sector_codes()`
- L58 `test_comparison_markdown_has_no_optional_tabulate_dependency()`
- L88 `test_summary_reports_untradable_separately_from_censored()`
- L114 `test_index_weight_snapshot_is_effective_next_trading_day()`
- L131 `test_signal_quantile_excludes_current_crash()`
- L161 `test_r0_cost_stop_and_boundary_handling()`
- L191 `test_r2_adds_after_observable_second_breakout()`

## tests/test_sector_panic_component_exit.py

[打开文件](../../tests/test_sector_panic_component_exit.py)

- L18 `_calendar(count=35)`
- L25 `_panel(codes, calendar, paths=None)`
- L47 `_selection(codes)`
- L55 `test_natr_is_pit_and_uses_adjusted_true_range()`
- L64 `test_natr_thresholds_are_derived_per_stock_without_future_data()`
- L75 `test_component_r4_exits_one_stock_while_another_remains_open()`
- L113 `test_component_stop_is_independent_and_does_not_sell_other_stocks()`
- L137 `test_component_limit_down_defers_only_that_stock()`
- L158 `test_component_missing_volatility_history_fails_closed()`
- L175 `test_paired_component_wrapper_runs_both_frozen_rules()`
- L189 `test_component_avwap_break_exits_after_prior_close_above_anchor()`
- L214 `test_avwap_state_requires_valid_daily_volume_and_is_entry_anchored()`
- L229 `test_r6_arms_on_rising_avwap_and_exits_on_confirmed_hwm_failure()`
- L257 `test_r6_requires_both_avwap_break_and_natr_drawdown()`
- L283 `test_r6_stop_has_priority_over_hybrid_failure()`

## tests/test_sector_panic_config.py

[打开文件](../../tests/test_sector_panic_config.py)

- L14 `_valid_config()`
- L56 `class TestDeepValidation`
- L57 `TestDeepValidation.test_valid_config_passes(self)`
- L60 `TestDeepValidation.test_negative_cost_rejected(self)`
- L66 `TestDeepValidation.test_missing_cost_field_rejected(self)`
- L72 `TestDeepValidation.test_empty_rules_rejected(self)`
- L78 `TestDeepValidation.test_negative_hold_days_rejected(self)`
- L84 `TestDeepValidation.test_empty_stops_rejected(self)`
- L90 `TestDeepValidation.test_positive_stop_rejected(self)`
- L96 `TestDeepValidation.test_non_candidate_gate_param_rejected(self)`
- L102 `TestDeepValidation.test_positive_absolute_threshold_rejected(self)`
- L108 `TestDeepValidation.test_negative_width_threshold_rejected(self)`
- L114 `TestDeepValidation.test_train_start_after_end_rejected(self)`
- L120 `TestDeepValidation.test_overlapping_splits_rejected(self)`
- L126 `TestDeepValidation.test_holdout_before_oos_end_rejected(self)`
- L132 `TestDeepValidation.test_oos_firewall_disabled_rejected(self)`
- L138 `TestDeepValidation.test_none_root_rejected_not_crash(self)`
- L143 `TestDeepValidation.test_holdout_invalid_calendar_date_rejected(self)`
- L151 `TestDeepValidation.test_holdout_string_form_valid(self)`
- L158 `TestDeepValidation.test_non_dict_universe_rejected(self)`
- L165 `TestDeepValidation.test_non_dict_nested_objects_rejected(self)`
- L173 `TestDeepValidation.test_non_numeric_values_rejected_without_crash(self)`
- L193 `TestDeepValidation.test_invalid_calendar_date_rejected(self)`
- L201 `TestDeepValidation.test_string_holdout_before_oos_end_rejected(self)`
- L209 `TestDeepValidation.test_string_holdout_after_oos_end_accepted(self)`
- L214 `TestDeepValidation.test_fractional_cost_is_not_truncated(self)`
- L220 `TestDeepValidation.test_blank_sector_description_rejected(self)`
- L226 `TestDeepValidation.test_train_script_cutoff_must_equal_train_end(self)`
- L232 `TestDeepValidation.test_manual_curated_requires_evidence_members(self)`

## tests/test_sector_panic_confirmation_close_reentry_v10.py

[打开文件](../../tests/test_sector_panic_confirmation_close_reentry_v10.py)

- L7 `_calendar(count=40)`
- L14 `_run(closes)`
- L45 `test_confirmation_floor_retries_after_below_floor_close()`
- L60 `test_confirmation_floor_does_not_allow_equal_price()`

## tests/test_sector_panic_confirmation_close_v10_lifecycle_report.py

[打开文件](../../tests/test_sector_panic_confirmation_close_v10_lifecycle_report.py)

- L10 `test_v10_lifecycle_page_contains_calculation_and_execution_nodes()`
- L33 `test_generated_v10_page_contains_full_sample_and_primary_orders()`

## tests/test_sector_panic_continuation_value_exit.py

[打开文件](../../tests/test_sector_panic_continuation_value_exit.py)

- L16 `_calendar(count=40)`
- L23 `_panel(path, calendar)`
- L48 `test_decision_features_and_label_use_only_causal_path()`
- L93 `test_loeo_never_scores_held_out_episode_in_training()`
- L114 `test_time_order_split_excludes_straddling_episode_and_marks_test()`
- L137 `test_missing_feature_is_kept_for_fail_closed_fallback()`
- L166 `test_unfilled_entry_cash_remains_in_event_daily_nav()`

## tests/test_sector_panic_cost.py

[打开文件](../../tests/test_sector_panic_cost.py)

- L14 `class TestRoundTripCost`
- L15 `TestRoundTripCost.test_consistent_three_field_structure(self)`
- L21 `TestRoundTripCost.test_inconsistent_round_trip_raises(self)`
- L25 `TestRoundTripCost.test_negative_cost_rejected(self)`
- L29 `TestRoundTripCost.test_from_bps_splits_evenly(self)`
- L35 `TestRoundTripCost.test_weighted_ratio(self)`
- L40 `class TestLegacyConversion`
- L43 `TestLegacyConversion.test_path_rules_round_trip_passthrough(self)`
- L47 `TestLegacyConversion.test_thresholds_per_side_doubled_20(self)`
- L51 `TestLegacyConversion.test_thresholds_per_side_doubled_100(self)`
- L54 `TestLegacyConversion.test_basket_gate_single_deduction(self)`
- L57 `TestLegacyConversion.test_assemble_strategy_v1_per_side(self)`
- L60 `TestLegacyConversion.test_unknown_script_raises(self)`

## tests/test_sector_panic_e2_lifecycle_report.py

[打开文件](../../tests/test_sector_panic_e2_lifecycle_report.py)

- L4 `test_state_operations_keep_decision_transitions_and_drop_incomplete_noise()`
- L47 `test_html_page_embeds_data_counts_and_interactive_controls()`

## tests/test_sector_panic_entry_confirmation_r0_forward_runner.py

[打开文件](../../tests/test_sector_panic_entry_confirmation_r0_forward_runner.py)

- L36 `_calendar(count=28)`
- L43 `_selection(codes)`
- L54 `_panel(codes, calendar, t1_closes)`
- L77 `test_scope_and_required_output_identity_are_frozen()`
- L87 `test_implementation_lock_matches_runner_and_rejects_tampering(tmp_path)`
- L98 `test_forward_filter_excludes_every_pre_freeze_signal()`
- L108 `test_frozen_estimators_are_deterministic_and_use_nearest_rank()`
- L119 `test_r8_candidate_is_r5_gate_composed_with_r0_and_keeps_cash()`
- L141 `test_entry_price_diagnostics_value_missed_winners_and_avoided_losses()`
- L166 `test_scope_file_still_has_forward_only_authority()`
- L173 `test_pit_prefix_allows_only_post_boundary_status_additions()`
- L190 `test_e1_daily_starts_at_t1_and_e2_is_non_trading_fixed_path()`
- L221 `test_portfolio_overlay_enforces_total_sector_and_cross_sector_stock_caps()`
- L247 `test_cross_runtime_revision_chain_records_changes_and_removals(tmp_path)`
- L278 `test_nonempty_forward_runner_is_byte_identical_across_two_runtimes(tmp_path, monkeypatch)`

## tests/test_sector_panic_entry_confirmation_r0_preflight.py

[打开文件](../../tests/test_sector_panic_entry_confirmation_r0_preflight.py)

- L24 `_scope()`
- L28 `test_scope_contract_is_owner_approved_and_hash_bound()`
- L45 `test_synthetic_proof_keeps_failed_gate_budgets_as_cash_and_uses_r0()`
- L57 `test_scope_rejects_exit_rule_drift()`
- L64 `test_scope_rejects_all_cash_gate_weakening()`
- L71 `test_locked_path_inventory_stays_inside_workspace()`

## tests/test_sector_panic_entry_review_buffer_v9.py

[打开文件](../../tests/test_sector_panic_entry_review_buffer_v9.py)

- L8 `_calendar(count=40)`
- L15 `_panel(calendar, closes, avwap_prices=None)`
- L31 `_item(calendar, **overrides)`
- L50 `_simulate(calendar, closes, *, mode='WAIT', structural=True, **kwargs)`
- L68 `test_delay_control_reviews_t_plus_one_and_fills_t_plus_two()`
- L82 `test_hard_review_rejects_a_broken_review_close_before_order()`
- L97 `test_active_floor_is_stricter_than_hard_structure_review()`
- L120 `test_half_natr_buffer_ignores_shallow_dual_break_then_exits_deeper_break()`
- L133 `test_buffer_does_not_delay_hard_higher_low_failure()`
- L145 `test_two_close_confirmation_delays_only_dual_failure()`
- L158 `test_review_order_uses_review_day_anchor_and_known_price_cap()`

## tests/test_sector_panic_entry_review_buffer_v9_lifecycle_report.py

[打开文件](../../tests/test_sector_panic_entry_review_buffer_v9_lifecycle_report.py)

- L8 `test_lifecycle_page_contains_v9_controls_and_nodes()`
- L14 `test_generated_page_has_all_stock_events_and_prices()`

## tests/test_sector_panic_extension_no_chase_v8.py

[打开文件](../../tests/test_sector_panic_extension_no_chase_v8.py)

- L19 `_calendar(count=40)`
- L26 `_panel(calendar, closes=None, avwap_prices=None)`
- L49 `_item(calendar, **overrides)`
- L68 `_simulate(calendar, panel, *, rule=V8_NCW_RULE_ID, mode='WAIT', structural=False, item=None, policy=None)`
- L86 `test_entry_at_both_frozen_limits_is_allowed()`
- L101 `test_skip_arm_abandons_an_extended_confirmation_without_order()`
- L116 `test_capped_close_order_does_not_fill_above_limit()`
- L133 `test_wait_arm_retries_after_rally_and_fills_later_pullback()`
- L150 `test_wait_window_never_targets_session_six()`
- L163 `test_below_active_anchor_is_not_counted_as_extension()`
- L177 `test_wait_arm_abandons_when_higher_low_breaks()`
- L189 `test_structural_failure_exits_next_close_before_wide_stop()`
- L206 `test_stop_has_label_priority_when_stop_and_structure_fail_together()`
- L222 `test_stop_and_mfe_audits_use_actual_confirmation_and_filled_sell()`
- L244 `test_event_cash_and_lower_tail_cvar_keep_unfilled_slots()`

## tests/test_sector_panic_extension_no_chase_v8_report.py

[打开文件](../../tests/test_sector_panic_extension_no_chase_v8_report.py)

- L4 `test_v8_report_defaults_to_full_universe_and_has_line_chart_drilldown()`

## tests/test_sector_panic_extension_no_chase_v8_report_r1.py

[打开文件](../../tests/test_sector_panic_extension_no_chase_v8_report_r1.py)

- L7 `test_report_r1_cleans_null_text_and_uses_mobile_ticks()`

## tests/test_sector_panic_extension_no_chase_v8_runner.py

[打开文件](../../tests/test_sector_panic_extension_no_chase_v8_runner.py)

- L22 `_event(rule_id, value)`
- L36 `test_factorial_event_identity_is_exact()`
- L60 `test_structural_counterfactual_keeps_same_slot_pairing()`
- L80 `test_scope_loader_refuses_unfrozen_scope(tmp_path)`
- L91 `test_replay_verification_checks_every_file_byte(tmp_path)`
- L107 `test_giveback_audit_can_compare_reidentified_q0_and_candidate()`

## tests/test_sector_panic_hold_sensitivity.py

[打开文件](../../tests/test_sector_panic_hold_sensitivity.py)

- L53 `test_r2_never_uses_a_second_breakout_after_the_exit()`
- L81 `test_r2_breakout_on_the_exit_day_does_not_add()`
- L94 `test_common_path_horizon_does_not_change_outcomes()`
- L114 `test_bootstrap_stat_is_deterministic_and_bounded()`
- L128 `test_date_cluster_bootstrap_keeps_same_day_events_together()`
- L138 `test_runtime_snapshot_detects_underlying_table_tampering(tmp_path)`
- L164 `test_paired_diff_stats_uses_only_the_common_support_set()`
- L215 `test_cell_metrics_counts_and_rates()`
- L269 `test_direction_check_is_mechanical()`
- L284 `test_equal_weight_aggregate_ignores_missing_sectors()`
- L295 `test_raw_path_curve_censors_at_the_next_event_boundary()`
- L320 `test_strategy_net_curve_is_flat_in_cash_after_exit()`
- L334 `test_strategy_net_curve_rebuilds_r2_position_sizing()`
- L362 `test_strategy_net_curve_half_weight_without_add()`
- L378 `test_stop_day_counts_histogram()`
- L400 `test_pooled_pairing_uses_sector_and_signal_id()`
- L422 `test_manifest_cache_validates_keys_and_output_hashes(tmp_path, monkeypatch)`
- L464 `test_cli_end_is_passed_to_run_arm(tmp_path, monkeypatch)`
- L514 `test_run_arm_passes_end_date_to_backtest(tmp_path, monkeypatch)`
- L548 `test_load_frozen_paths_converts_absolute_positions_to_relative_days(monkeypatch)`
- L575 `_event_frame(ids)`
- L584 `test_event_identity_rejects_same_count_with_changed_order_or_components(tmp_path, monkeypatch)`
- L608 `test_candidate_tolerances_use_pre_2026_pool_only()`
- L648 `test_candidate_requires_positive_sector_majority_and_nonzero_medians()`
- L690 `test_arm_loader_uses_manifest_primary_cost_not_first_row(tmp_path, monkeypatch)`
- L708 `test_formal_20d_comparison_allows_only_path_type_difference(tmp_path, monkeypatch)`
- L738 `test_analysis_output_metadata_detects_tampering(tmp_path)`

## tests/test_sector_panic_integrity.py

[打开文件](../../tests/test_sector_panic_integrity.py)

- L11 `test_current_rows_treats_missing_sequence_as_zero_and_selects_latest()`
- L24 `test_supersede_chain_reports_dangling_reference()`
- L42 `_layer_frames(q1_quality='NO_Q1_WITHIN_WINDOW', q2_quality='NO_Q1_WITHIN_WINDOW')`
- L83 `test_e2_confirmed_q1_unconfirmed_is_a_legal_cross_layer_state()`
- L90 `test_q2_eligible_without_q1_confirmation_is_rejected()`

## tests/test_sector_panic_natr_stop_presentation_v2.py

[打开文件](../../tests/test_sector_panic_natr_stop_presentation_v2.py)

- L4 `test_presentation_v2_shows_all_arm_positions_exits_and_cap20_marker()`

## tests/test_sector_panic_natr_stop_report.py

[打开文件](../../tests/test_sector_panic_natr_stop_report.py)

- L4 `test_natr_stop_html_contains_primary_arm_comparison_and_stop_lines()`

## tests/test_sector_panic_phase1_execution.py

[打开文件](../../tests/test_sector_panic_phase1_execution.py)

- L24 `_calendar(count=40)`
- L31 `_panel(codes, calendar, paths=None, amounts=None)`
- L59 `_selection(codes)`
- L68 `_universe(codes, calendar)`
- L76 `_sha(path)`
- L80 `test_phase1_scope_freezes_risk_policy_and_locked_parent_hashes()`
- L104 `test_selection_is_signal_date_causal_and_tie_breaks_by_code()`
- L130 `test_limit_up_entry_keeps_cash_and_never_substitutes()`
- L155 `test_r4_activates_then_trails_and_sells_on_next_close()`
- L179 `test_stop_has_priority_and_limit_down_defers_final_liquidation()`
- L207 `test_hwm_is_frozen_after_trailing_exit_submission()`
- L229 `test_next_event_boundary_preempts_day20_and_executes_same_close()`
- L247 `test_day20_boundary_and_cost_ledger_are_exact()`
- L265 `test_missing_exact_limit_on_exit_fails_closed_but_keeps_retrying()`
- L288 `test_paired_execution_uses_same_selection_and_revision_keys_are_unique()`
- L314 `test_execution_closure_rejects_broken_nav_identity()`

## tests/test_sector_panic_regime.py

[打开文件](../../tests/test_sector_panic_regime.py)

- L28 `make_index(closes: list[float], start_date: int=20160101)`
- L41 `make_flat_index(close: float, n: int, start_date: int=20160101)`
- L45 `trade_days_for(frame: pd.DataFrame)`
- L52 `class TestInputValidation`
- L53 `TestInputValidation.test_empty_frame_raises(self)`
- L57 `TestInputValidation.test_missing_columns_raises(self)`
- L63 `TestInputValidation.test_duplicate_dates_raise(self)`
- L72 `TestInputValidation.test_non_positive_close_raises(self)`
- L81 `TestInputValidation.test_nan_close_raises(self)`
- L93 `class TestRollingQuantileOfRets`
- L94 `TestRollingQuantileOfRets.test_excludes_current_value(self)`
- L109 `TestRollingQuantileOfRets.test_monotonic_input_gives_stable_quantile(self)`
- L122 `class TestRollingBetaSeries`
- L123 `TestRollingBetaSeries.test_beta_equals_one_for_identical_series(self)`
- L129 `TestRollingBetaSeries.test_beta_zero_for_unrelated_series(self)`
- L136 `TestRollingBetaSeries.test_min_periods_enforced(self)`
- L144 `class TestRegimeClassification`
- L145 `TestRegimeClassification.test_unknown_when_insufficient_history(self)`
- L152 `TestRegimeClassification.test_sector_local_when_no_tails(self)`
- L159 `TestRegimeClassification.test_alignment_by_trade_date_not_tail(self)`
- L169 `TestRegimeClassification.test_series_output_shape(self)`
- L179 `TestRegimeClassification.test_series_matches_single_date_classification(self)`
- L198 `TestRegimeClassification.test_spring_festival_exchange_days_are_contiguous(self)`
- L222 `TestRegimeClassification.test_unknown_when_residual_quantile_not_accumulated(self)`
- L233 `TestRegimeClassification.test_non_unknown_after_residual_quantile_accumulated(self)`
- L242 `TestRegimeClassification.test_common_missing_weekday_fails_closed(self)`

## tests/test_sector_panic_repair_quality_r7.py

[打开文件](../../tests/test_sector_panic_repair_quality_r7.py)

- L15 `_component(code, rule, filled, contribution)`
- L28 `test_uplift_decomposition_adds_exactly_to_event_uplift()`
- L56 `test_unknown_episode_covariates_remain_missing_without_imputation()`

## tests/test_sector_panic_repair_quality_report.py

[打开文件](../../tests/test_sector_panic_repair_quality_report.py)

- L7 `test_state_operations_include_q1_break_and_hold_markers()`
- L18 `test_html_page_contains_five_arm_table_and_same_axis_chart()`
- L39 `test_report_script_can_run_as_a_direct_cli()`

## tests/test_sector_panic_repair_quality_runner.py

[打开文件](../../tests/test_sector_panic_repair_quality_runner.py)

- L23 `test_runtime_read_contract_includes_index_daily_for_relative_strength_audit()`
- L27 `test_json_safe_converts_nonfinite_statistics_to_null_values()`
- L33 `test_runner_refuses_unfrozen_scope()`
- L50 `test_pair_events_keeps_attribution_and_deployment_layers_separate()`
- L84 `test_event_context_broadcasts_one_event_context_to_all_five_arms()`
- L104 `test_replay_verification_rejects_different_bytes(tmp_path)`
- L118 `test_replay_verification_accepts_identical_files(tmp_path)`
- L134 `test_baseline_replay_comparison_counts_changed_ledgers()`

## tests/test_sector_panic_trade_timing_presentation_v3.py

[打开文件](../../tests/test_sector_panic_trade_timing_presentation_v3.py)

- L4 `test_trade_timing_page_shows_identification_and_arm_execution_prices()`

## tests/test_sector_panic_v10_h1_mech_half.py

[打开文件](../../tests/test_sector_panic_v10_h1_mech_half.py)

- L11 `_panel(dates, prices)`
- L29 `_parent()`
- L48 `_attempts()`
- L71 `_daily()`
- L82 `test_trigger_ledger_rebuilds_v10_buffered_structure_and_freezes_145()`
- L97 `test_trigger_ledger_does_not_treat_raw_only_dual_failure_as_v10_failure()`
- L117 `test_h1_sells_half_once_and_keeps_parent_result_for_residual()`
- L148 `test_parent_exit_priority_blocks_boundary_due_date()`

## tests/test_sector_panic_v10_max_hold_path_runner.py

[打开文件](../../tests/test_sector_panic_v10_max_hold_path_runner.py)

- L19 `_workspace_tmp()`
- L24 `test_forbid_writing_inside_frozen_runtime()`
- L36 `test_report_states_exploratory_and_does_not_change_kill()`
- L64 `test_runner_writes_sidecar_not_frozen()`
- L73 `_run_sidecar_case(tmp_path, runtime, out)`

## tests/test_sector_panic_v14_confirmation_floor_epsilon.py

[打开文件](../../tests/test_sector_panic_v14_confirmation_floor_epsilon.py)

- L25 `_calendar(count=40)`
- L32 `_inputs(closes, *, natr20=0.05)`
- L57 `_simulate(closes, *, epsilon=False, review_sessions=0, review_mode='NONE', natr20=0.05)`
- L70 `test_frozen_v10_engine_bytes_are_unchanged()`
- L76 `test_epsilon_natr_is_frozen_at_quarter()`
- L87 `test_predicate_has_no_return_inputs()`
- L96 `test_predicate_band_and_integrity()`
- L126 `test_engine_flag_off_matches_v10_floor_reject()`
- L151 `test_engine_epsilon_fills_inside_band_and_marks()`
- L166 `test_engine_epsilon_still_fills_strictly_above_c()`
- L178 `test_engine_epsilon_rejects_at_or_below_floor()`
- L190 `test_engine_does_not_relax_price_above_limit()`
- L200 `test_engine_does_not_rescue_structure_broken()`
- L213 `test_missing_natr_is_integrity_failure()`
- L222 `test_epsilon_requires_confirmation_floor_flag()`
- L255 `test_post_entry_path_does_not_change_fill()`

## tests/test_sector_panic_v14_forward_marker.py

[打开文件](../../tests/test_sector_panic_v14_forward_marker.py)

- L28 `test_v14_scope_is_marker_only_and_non_writing()`
- L41 `test_v14_preflight_reads_no_returns_and_writes_nothing()`
- L53 `test_v14_execution_request_fails_closed(capsys)`
- L61 `test_v14_scope_rejects_execution_authority()`
- L76 `test_v14_scope_rejects_epsilon_retune_and_food()`
- L88 `test_v14_forward_boundary_rejects_history()`
- L100 `test_v14_safe_output_rejects_v10_v12_v13_roots()`
- L114 `_forward_panel(closes)`
- L142 `test_dual_arm_in_memory_rejects_historical_signal()`
- L153 `test_dual_arm_in_memory_control_rejects_band_candidate_fills()`

## tests/test_sector_panic_v8_trade_lifecycle_report.py

[打开文件](../../tests/test_sector_panic_v8_trade_lifecycle_report.py)

- L4 `test_lifecycle_report_contains_v8_nodes_regions_and_drilldown()`

## tests/test_sector_structural_feasibility.py

[打开文件](../../tests/test_sector_structural_feasibility.py)

- L18 `_calendar(count=50)`
- L25 `_universe(codes, start=20240102, end=20991231)`
- L33 `_ready_panel(codes, calendar, path_by_code=None, amount_by_code=None)`
- L60 `test_diagnostic_panel_carries_only_audited_suspension()`
- L91 `test_signal_diagnostic_uses_pit_breadth_and_first_trigger()`
- L122 `test_capture_separates_selected_and_limit_up_blocked_paths()`
- L165 `test_actual_filled_path_retains_blocked_target_weight_as_cash()`
- L201 `test_stop_realizability_records_limit_down_deferred_liquidation()`
- L238 `test_missing_filled_component_path_fails_closed()`
- L264 `test_direct_trail_requires_activation_then_later_hwm_drawdown()`
- L295 `test_overlapping_cross_sector_windows_form_one_macro_episode()`
- L312 `test_blocked_entry_summary_is_conditional_on_limit_up_events()`
- L337 `test_episode_robustness_reports_leave_one_episode_out_proxy()`

## tests/test_shadow_execution_failure.py

[打开文件](../../tests/test_shadow_execution_failure.py)

- L16 `class TestShadowExecutionFailure`
- L19 `TestShadowExecutionFailure.test_ready_orders_empty_fills_is_fail(self)`
- L46 `TestShadowExecutionFailure.test_ready_orders_zero_executed_is_fail(self)`
- L68 `TestShadowExecutionFailure.test_partial_execution_is_ok(self)`
- L87 `TestShadowExecutionFailure.test_overall_verdict_fail_when_execution_fails(self)`
- L107 `TestShadowExecutionFailure.test_overall_verdict_skipped_when_no_fail(self)`
- L128 `TestShadowExecutionFailure.test_high_slippage_counted_as_executed(self)`

## tests/test_shadow_execution_price_precheck.py

[打开文件](../../tests/test_shadow_execution_price_precheck.py)

- L20 `class TestShadowExecutionPricePrecheck`
- L23 `TestShadowExecutionPricePrecheck.test_ready_orders_missing_exec_prices_is_fail(self)`
- L50 `TestShadowExecutionPricePrecheck.test_no_next_trade_day_is_skipped(self)`
- L76 `TestShadowExecutionPricePrecheck.test_price_precheck_returns_early_before_paper_broker(self)`
- L113 `TestShadowExecutionPricePrecheck.test_prices_present_proceeds_to_execution(self)`
- L148 `class TestShadowHighSlippageCounted`
- L151 `TestShadowHighSlippageCounted.test_high_slippage_counted_in_n_executed(self)`
- L173 `TestShadowHighSlippageCounted.test_only_high_slippage_still_counts_as_executed(self)`
- L192 `class TestShadowPrecheckAuditRecord`
- L195 `TestShadowPrecheckAuditRecord.test_precheck_fail_audit_record_structure(self)`
- L221 `TestShadowPrecheckAuditRecord.test_precheck_skip_audit_record_structure(self)`

## tests/test_shadow_summary.py

[打开文件](../../tests/test_shadow_summary.py)

- L15 `class TestShadowSummaryCounting`
- L18 `TestShadowSummaryCounting.test_ok_and_skipped_returns_zero(self, tmp_path)`
- L44 `TestShadowSummaryCounting.test_all_skipped_returns_zero(self)`
- L65 `TestShadowSummaryCounting.test_fail_and_skipped_returns_one(self)`

## tests/test_shenwan_l1_daily.py

[打开文件](../../tests/test_shenwan_l1_daily.py)

- L7 `test_contracted_codes_are_product_l1_not_full_sw2021()`
- L15 `test_sw_daily_maps_pct_change_and_pre_close()`

## tests/test_shock_reversal.py

[打开文件](../../tests/test_shock_reversal.py)

- L35 `_make_limit_df(ts_codes: list, dates: list, down_limits: dict=None)`
- L59 `_make_raw_price_df(ts_codes: list, dates: list, closes: dict=None)`
- L89 `class TestLimitDownFilter`
- L92 `TestLimitDownFilter.test_down_limit_notna_does_not_trigger(self)`
- L127 `TestLimitDownFilter.test_actual_limit_down_zeroes_signal(self)`
- L170 `TestLimitDownFilter.test_limit_down_with_tolerance(self)`
- L199 `TestLimitDownFilter.test_no_limit_data_returns_unchanged(self)`
- L220 `class TestSignalDirection`
- L223 `TestSignalDirection.test_severity_increases_with_drop(self)`
- L238 `TestSignalDirection.test_below_threshold_is_zero(self)`
- L252 `class TestFilterSemantics`
- L255 `TestFilterSemantics.test_st_filter_produces_nan(self)`
- L265 `TestFilterSemantics.test_st_filter_non_st_unchanged(self)`
- L275 `TestFilterSemantics.test_ipo_filter_sets_nan(self)`
- L286 `TestFilterSemantics.test_old_stock_unchanged(self)`
- L302 `class TestAmountFilter`
- L305 `TestAmountFilter.test_low_amount_set_to_nan(self)`
- L332 `class TestFactorSpec`
- L335 `TestFactorSpec.test_factor_spec_exists(self)`
- L339 `TestFactorSpec.test_factor_params_present(self)`
- L351 `TestFactorSpec.test_sign_is_positive(self)`
- L355 `TestFactorSpec.test_category_is_shock_reversal(self)`
- L364 `class TestSuspendLookback`
- L367 `TestSuspendLookback.test_lookback_at_least_2_years(self)`
- L374 `TestSuspendLookback.test_lookback_handles_early_dates(self)`
- L387 `class TestShockCSConfigRouting`
- L390 `TestShockCSConfigRouting.test_nested_section_reads_missing_method_drop(self)`
- L402 `TestShockCSConfigRouting.test_nested_section_reads_correct_neutralizers(self)`
- L417 `TestShockCSConfigRouting.test_missing_section_raises_runtime_error(self)`
- L428 `TestShockCSConfigRouting.test_no_section_preserves_backward_compat(self)`
- L438 `class TestShockCSNaNNotBackfilled`
- L441 `TestShockCSNaNNotBackfilled.test_structural_nan_removed_not_filled(self)`
- L491 `TestShockCSNaNNotBackfilled.test_factor_panel_shock_cs_uses_drop(self)`
- L504 `TestShockCSNaNNotBackfilled.test_build_script_not_fallback_to_default(self)`

## tests/test_sleeve_performance_overlay.py

[打开文件](../../tests/test_sleeve_performance_overlay.py)

- L18 `_make_dates(n: int=40)`
- L22 `_make_scores_and_returns(dates: list[int], n_stocks: int=60, seed: int=7)`
- L63 `_overlay_config(**overrides)`
- L81 `test_positive_sleeve_is_amplified_and_negative_sleeve_is_compressed()`
- L105 `test_insufficient_history_uses_neutral_multiplier()`
- L123 `test_future_forward_returns_do_not_affect_current_multiplier()`
- L148 `test_disabled_overlay_returns_empty_frames()`

## tests/test_smoke_cache_isolation.py

[打开文件](../../tests/test_smoke_cache_isolation.py)

- L21 `class TestSmokeNeverCallsPhase1`
- L24 `TestSmokeNeverCallsPhase1.test_smoke_does_not_call_run_phase1(self)`
- L48 `TestSmokeNeverCallsPhase1.test_no_recompute_flag_exists(self)`
- L63 `class TestSmokeCacheIsolation`
- L66 `TestSmokeCacheIsolation.test_write_factor_uses_year_month_partitions(self)`
- L101 `TestSmokeCacheIsolation.test_write_factor_short_window_does_not_delete_other_months(self)`

## tests/test_smoke_phase2_readonly.py

[打开文件](../../tests/test_smoke_phase2_readonly.py)

- L23 `_make_smoke_args(start='20160101', end='20160229', dry_run=True)`
- L37 `class TestSmokeNeverCallsPhase1`
- L40 `TestSmokeNeverCallsPhase1.test_smoke_does_not_call_run_phase1(self)`
- L59 `TestSmokeNeverCallsPhase1.test_smoke_passes_no_recompute_to_phase2(self)`
- L99 `class TestSmokeCacheIsolation`
- L102 `TestSmokeCacheIsolation.test_smoke_factor_cache_untouched(self)`
- L109 `TestSmokeCacheIsolation.test_no_recompute_flag_blocks_phase1_rebuild_in_phase2(self)`
- L132 `class TestSmokePhase2Integration`
- L135 `TestSmokePhase2Integration.test_phase2_not_skipped_when_factors_exist(self)`
- L146 `TestSmokePhase2Integration.test_factor_coverage_count_includes_factors_with_dupes(self)`

## tests/test_smoke_short_window.py

[打开文件](../../tests/test_smoke_short_window.py)

- L22 `_make_args(start='20160101', end='20160229')`
- L30 `class TestSmokeShortWindow`
- L33 `TestSmokeShortWindow.test_smoke_calendar_variable_exists(self)`
- L59 `TestSmokeShortWindow.test_smoke_phase2_short_window_mocked(self)`
- L91 `TestSmokeShortWindow.test_short_window_classification_logic(self)`
- L106 `TestSmokeShortWindow.test_smoke_phase2_no_calendar_name_error(self)`

## tests/test_strategy_alpha_failure_diagnosis.py

[打开文件](../../tests/test_strategy_alpha_failure_diagnosis.py)

- L49 `_make_mock_runs_df(strategies: list[str] | None=None, years: list[int] | None=None)`
- L82 `_make_mock_period_data(strategies: list[str] | None=None, years: list[int] | None=None, seed: int=42, with_benchmark_conflict: bool=False)`
- L150 `class TestBenchmarkConflict`
- L151 `TestBenchmarkConflict.test_detects_same_period_benchmark_conflict(self)`
- L164 `TestBenchmarkConflict.test_no_conflict_when_benchmarks_match(self)`
- L175 `TestBenchmarkConflict.test_conflict_marks_excess_unreliable(self)`
- L192 `class TestInvestmentGateWithBenchmark`
- L193 `TestInvestmentGateWithBenchmark.test_no_go_absolute_return_still_valid_during_conflict(self)`
- L210 `TestInvestmentGateWithBenchmark.test_gate_has_benchmark_status_fields(self)`
- L226 `class TestStrictFactorRetentionGate`
- L227 `TestStrictFactorRetentionGate.test_missing_long_only_top_fails_retention(self)`
- L240 `TestStrictFactorRetentionGate.test_negative_top_excess_fails_retention(self)`
- L252 `TestStrictFactorRetentionGate.test_retention_failure_reasons_populated(self)`
- L264 `TestStrictFactorRetentionGate.test_scorecard_has_all_required_fields(self)`
- L284 `class TestRouterOracle`
- L285 `TestRouterOracle.test_opportunity_cost_has_oracle_fields(self)`
- L322 `TestRouterOracle.test_signal_date_not_all_zero(self)`
- L350 `TestRouterOracle.test_insufficient_data_when_no_sleeve_scores(self)`
- L371 `TestRouterOracle.test_oracle_marks_unmapped_signal_dates_out_of_window(self)`
- L419 `TestRouterOracle.test_oracle_ok_rows_have_nonzero_period_end(self)`
- L450 `TestRouterOracle.test_hindsight_oracle_excludes_non_ok_rows(self)`
- L478 `TestRouterOracle.test_oracle_report_stats_use_ok_rows_only(self)`
- L521 `class TestConstructionDiagnostics`
- L522 `TestConstructionDiagnostics.test_pre_post_cost_separated(self)`
- L540 `TestConstructionDiagnostics.test_rebalance_topn_stubs_are_not_available(self)`
- L557 `class TestReportGeneration`
- L558 `TestReportGeneration.test_investment_gate_has_all_required_columns(self)`
- L575 `TestReportGeneration.test_investment_status_valid_enum(self)`
- L584 `TestReportGeneration.test_normalized_has_reliability_fields(self)`
- L596 `class TestArtifactConsistency`
- L597 `TestArtifactConsistency.test_detects_missing_files(self)`
- L608 `TestArtifactConsistency.test_detects_template_artifacts(self)`
- L622 `TestArtifactConsistency.test_passes_when_clean(self)`
- L641 `class TestEdgeCases`
- L642 `TestEdgeCases.test_single_strategy_no_conflict_possible(self)`
- L649 `TestEdgeCases.test_empty_runs_handled(self)`
- L662 `TestEdgeCases.test_run_health_go_not_production_go(self)`
- L677 `class TestUtilities`
- L678 `TestUtilities.test_compound_basic(self)`
- L684 `TestUtilities.test_annualize(self)`
- L690 `TestUtilities.test_max_drawdown(self)`
- L698 `TestUtilities.test_ir(self)`

## tests/test_t0_cluster_duration_predictor.py

[打开文件](../../tests/test_t0_cluster_duration_predictor.py)

- L18 `_closes(values, start=20260105)`
- L23 `test_consecutive_down_days_counts_only_ending_streak()`
- L31 `test_window_depth_uses_only_lagged_history()`
- L46 `test_frozen_combinations_do_not_search_thresholds()`
- L63 `test_join_labels_does_not_change_feature_columns()`
- L107 `test_cluster_duration_uses_first_trigger_gap_rule()`
- L126 `test_path_return_requires_frozen_selected_names_and_ignores_other_codes()`
- L139 `test_combination_gate_kills_when_net_cannot_cover_costs()`

## tests/test_t0_mechanism_quintiles.py

[打开文件](../../tests/test_t0_mechanism_quintiles.py)

- L40 `_closes(values, start=20260105)`
- L52 `test_concentration_ratio_uses_absolute_value_and_stays_positive()`
- L61 `test_concentration_ratio_is_nan_when_denominator_tiny()`
- L70 `test_concentration_ratio_missing_date_is_nan()`
- L79 `test_intraday_seal_yzi_and_open_reseal_shares()`
- L105 `test_intraday_seal_returns_nan_when_no_active_codes()`
- L111 `test_intraday_seal_excludes_suspended()`
- L139 `test_l2_labels_map_to_next_open_trading_day()`
- L158 `test_l2_labels_nan_when_signal_missing_for_next_day()`
- L178 `_synthetic_packed(sector_close_values, panel_close_map, calendar, sector='electronics')`
- L192 `test_l4_path_minus_100bp_and_min_names_guard()`
- L219 `test_l4_nan_when_fewer_than_min_path_names()`
- L234 `test_l3_mdd_below_two_pct_flags_true()`
- L254 `test_l3_mdd_at_or_below_minus_two_pct_flags_false()`
- L273 `test_l4x_appendix_columns_present_in_paths_output()`
- L298 `_labeled_fixture(streak_values, extras=None)`
- L327 `test_streak_bin_edges_are_pre_registered()`
- L335 `test_streak_bin_table_counts_are_correct_at_boundaries()`
- L348 `test_quintile_bucketing_rank_based_ties()`
- L367 `test_quintile_edge_columns_are_descriptive_not_thresholds()`
- L384 `test_shock_source_unknown_kept_separate_and_underpowered_gated()`
- L402 `test_c1_contrast_emits_exactly_two_rows()`
- L412 `test_c1_contrast_underpowered_masks_metrics()`
- L426 `test_module_emits_no_predicted_single_columns_anywhere()`
- L436 `test_scope_yaml_forbids_search_and_recommendations()`
- L445 `test_appendix_cost_constants_match_plan()`

## tests/test_tradable_limit_rules.py

[打开文件](../../tests/test_tradable_limit_rules.py)

- L12 `class TestLimitRules`
- L15 `TestLimitRules.test_limit_up_open_blocks_buy(self)`
- L44 `TestLimitRules.test_limit_down_open_blocks_sell(self)`
- L69 `TestLimitRules.test_limit_check_unavailable_without_prices(self)`
- L90 `TestLimitRules.test_suspend_without_open_is_not_limit_unknown(self)`
- L121 `TestLimitRules.test_normal_stock_buyable(self)`
- L149 `class TestExecutionEdgeCases`
- L152 `TestExecutionEdgeCases.test_frozen_weight_not_rescaled(self)`
- L170 `TestExecutionEdgeCases.test_sell_generates_turnover_and_cost(self)`
- L186 `class TestLimitCacheIsolation`
- L189 `TestLimitCacheIsolation.test_no_limit_then_with_limit_not_reuse_cache(self)`
- L224 `TestLimitCacheIsolation.test_with_limit_then_without_limit_reuse_is_ok(self)`
- L258 `class TestBacktestPriceLimitPath`
- L261 `TestBacktestPriceLimitPath.test_raw_open_at_up_limit_cannot_buy(self)`
- L292 `TestBacktestPriceLimitPath.test_raw_open_at_down_limit_cannot_sell(self)`
- L321 `TestBacktestPriceLimitPath.test_auto_fetch_limit_data_triggers(self)`
- L351 `class TestBacktesterToTradableMaskIntegration`
- L359 `TestBacktesterToTradableMaskIntegration.test_simulate_passes_limit_data_to_get_mask(self)`
- L458 `TestBacktesterToTradableMaskIntegration.test_simulate_limit_up_stock_excluded_from_buys(self)`

## tests/test_turnover_controls.py

[打开文件](../../tests/test_turnover_controls.py)

- L13 `class TestNoTradeBand`
- L16 `TestNoTradeBand.test_small_changes_skip_trade(self)`
- L27 `TestNoTradeBand.test_large_changes_proceed(self)`
- L37 `TestNoTradeBand.test_mixed_changes(self)`
- L50 `class TestMaxWeightChange`
- L53 `TestMaxWeightChange.test_weight_sum_one_after_cap(self)`
- L64 `TestMaxWeightChange.test_floor_at_zero_long_only(self)`
- L75 `TestMaxWeightChange.test_new_stock_with_no_previous(self)`
- L86 `class TestBufferSelection`
- L89 `TestBufferSelection.test_retain_holdings_within_exit_rank(self)`
- L111 `TestBufferSelection.test_force_exit_below_exit_rank(self)`
- L128 `TestBufferSelection.test_no_previous_positions_falls_back_to_simple(self)`
- L142 `TestBufferSelection.test_retain_priority_over_new_candidates(self)`
- L167 `class TestScoreSmoothing`
- L170 `TestScoreSmoothing.test_smoothing_reduces_dispersion(self)`
- L187 `TestScoreSmoothing.test_zero_halflife_no_change(self)`

## tests/test_universe_date_lookback.py

[打开文件](../../tests/test_universe_date_lookback.py)

- L8 `test_universe_load_uses_yyyymmdd_lookback_start()`

## tests/test_v10_action_value_dataset.py

[打开文件](../../tests/test_v10_action_value_dataset.py)

- L18 `test_bt_matches_atomic_or_and_equality_does_not_fail()`
- L74 `test_remaining_hold_ignores_future_event_boundary()`
- L80 `test_first_observation_does_not_look_forward_for_structure()`
- L113 `test_y_full_bridges_h1_uplift()`
- L126 `_panel(dates, prices)`
- L144 `test_parent_exit_priority_zero_label_and_disabled()`
- L228 `test_frozen_trigger_counts_regression()`
- L238 `test_truncated_calendar_is_integrity_error_not_zero_label()`
- L316 `_label_fixture_parent_attempts()`
- L382 `test_missing_next_day_panel_row_is_data_failure_error()`
- L404 `test_missing_all_future_panel_rows_is_conflict_or_data_error()`
- L426 `test_same_price_real_fill_keeps_zero_label()`
- L446 `test_future_unresolved_flat_does_not_change_t_eligibility()`

## tests/test_v10_action_value_model.py

[打开文件](../../tests/test_v10_action_value_model.py)

- L16 `test_equal_episode_weights_sum_to_n_and_equal_across_episodes()`
- L30 `test_standardize_and_ridge_hand_calculation()`
- L50 `test_assign_episode_splits_purges_cross_cutoff()`
- L116 `test_fit_block_returns_no_feature_variation_when_both_constant()`
- L196 `test_fit_block_rejects_extra_columns_and_uses_whitelist_only()`

## tests/test_v10_action_value_runner_guards.py

[打开文件](../../tests/test_v10_action_value_runner_guards.py)

- L13 `test_run_id_rejects_path_escape()`
- L26 `test_freeze_refuses_already_frozen_scope()`

## tests/test_v10_delayed_structure_path_check.py

[打开文件](../../tests/test_v10_delayed_structure_path_check.py)

- L17 `test_classify_delta_sign_is_frozen()`
- L24 `test_observation_index_uses_component_sessions_not_calendar()`
- L38 `_panel(dates, prices)`
- L56 `_parent()`
- L78 `_attempts(*, sell_decision=20200110, sell_date=20200110, sell_price=100.0)`
- L109 `_daily_anchor()`
- L174 `test_y_k_uses_observation_next_session_not_trigger_next_session()`
- L216 `test_parent_submit_on_observation_date_is_priority_zero()`
- L238 `test_structure_failure_without_parent_submit_is_integrity_error()`
- L258 `test_post_observation_price_change_does_not_change_delta()`
- L285 `test_k2_cannot_override_primary_disposition()`
- L336 `test_evaluate_requires_hypothesized_positive_median()`
- L363 `test_assign_validation_uses_episode_start_not_observation_date()`
- L389 `test_frozen_h1_trigger_counts_still_hold()`

## tests/test_v10_max_hold_path_diagnostic.py

[打开文件](../../tests/test_v10_max_hold_path_diagnostic.py)

- L16 `test_round_trip_net_matches_budget_identity()`
- L26 `test_early_exit_requires_that_session_on_the_path()`
- L50 `test_engine_max_hold_path_reconstructs_and_early_exit_uses_same_close()`
- L97 `test_summaries_label_max_hold_as_winning_bucket_when_early_exit_hurts()`
- L136 `test_build_outputs_from_minimal_ledgers()`

## tests/test_v10_selective_exit_replay.py

[打开文件](../../tests/test_v10_selective_exit_replay.py)

- L14 `_panel(dates, prices, code='A.SH')`
- L32 `_books()`
- L150 `test_all_select_differs_from_none_select()`
- L188 `test_selective_mask_only_selected_key()`
- L216 `test_bootstrap_keeps_duplicate_episode_weight()`
- L231 `test_loo_drops_one_episode()`
- L247 `test_paired_event_uplift_rejects_missing_event()`
- L266 `test_paired_event_uplift_rejects_nan_return()`
- L285 `test_selection_trigger_map_requires_eligible()`

## tests/test_v11_confirmation_invalidation.py

[打开文件](../../tests/test_v11_confirmation_invalidation.py)

- L13 `_calendar(count=40)`
- L20 `_simulate(closes, *, max_hold=8, stop_distance=0.2, avwap=98.0, **kwargs)`
- L53 `_fill_then(after_entry)`
- L63 `test_two_closes_below_confirmation_exit_next_session()`
- L77 `test_t1_red_versus_entry_but_above_c_does_not_invalidate()`
- L87 `test_one_close_below_c_then_recover_resets_count()`
- L94 `test_second_close_due_on_boundary_is_not_economic_early_exit()`
- L105 `test_stop_has_priority_over_invalidation()`
- L112 `test_suspend_does_not_increment_or_reset_count()`
- L149 `test_blocked_sell_does_not_retry_past_boundary()`
- L188 `test_winner_retention_rejects_missing_v11_key()`
- L205 `test_winner_retention_counts_only_causal_earlier_invalidation()`
- L238 `test_runner_refuses_v10_output_directory()`
- L249 `test_runner_refuses_unlocked_v10_source_directory()`
- L263 `test_runner_rejects_parent_engine_hash_drift()`
- L280 `test_incomplete_event_is_not_dropped_from_economic_statistics()`

## tests/test_v12_evidence_stack.py

[打开文件](../../tests/test_v12_evidence_stack.py)

- L26 `_daily(session, date, decision, repair=98.0, **flags)`
- L46 `_features(rows, *, c=100.0, entry=101.0, natr=0.05, boundary=20, suspend=None, ranges=None)`
- L58 `test_session_zero_records_close_but_does_not_enter_watch()`
- L73 `test_suspend_holds_count_and_does_not_reset_watch()`
- L92 `test_reclaim_then_second_break_restarts_count()`
- L107 `test_strong_disprove_is_watch_and_repair_break_not_two_closes()`
- L136 `test_structure_overlap_flag_is_not_the_trigger()`
- L149 `test_labels_are_not_inputs_to_session_features()`
- L169 `test_vol_reexpansion_uses_natr_not_final_return()`
- L181 `test_scheduled_boundary_prefers_next_event_inside_20_sessions()`
- L200 `test_unresolved_classification_is_retry_policy_not_missing_data()`
- L213 `_component(rule_id, **values)`
- L226 `test_frozen_ledgers_classify_the_two_v11_holes()`
- L246 `test_unresolved_audit_locks_both_known_names()`
- L302 `test_runner_refuses_to_write_inside_frozen_v10_or_v11()`
- L315 `test_runner_requires_scope_locked_input_and_output_directories()`
- L340 `test_fill_summary_keeps_labels_off_the_feature_clock()`
- L368 `test_episode_diagnostic_counts_only_first_candidate_as_independent()`

## tests/test_v12_evidence_stack_engine.py

[打开文件](../../tests/test_v12_evidence_stack_engine.py)

- L15 `_daily_rows(values)`
- L27 `_lookup(dates)`
- L45 `test_v12_first_break_below_both_levels_is_a_trigger()`
- L64 `test_v12_target_on_boundary_is_observed_but_not_early()`
- L82 `test_v12_frozen_replay_outputs_are_complete_and_reproduced()`

## tests/test_v12_r1_engine_integrity.py

[打开文件](../../tests/test_v12_r1_engine_integrity.py)

- L27 `_calendar(count=40)`
- L34 `_concat(results, name)`
- L39 `_simulate(*, close_overrides=None, item_overrides=None, suspended=(), down_limit=(), incomplete_limit=(), code='A.SH', selected_count=1, max_hold=20, next_event_boundary_position=None, enable_v12=True, rule_id=V12_R1_RULE_ID)`
- L115 `_clone(result)`
- L119 `test_r1_first_break_below_both_levels_exits_next_session()`
- L145 `test_r1_trigger_day_stop_owns_and_retains_structural_provenance()`
- L162 `test_r1_same_session_invalidation_outranks_structural_failure()`
- L182 `test_r1_prior_structural_order_is_immutable_when_candidate_arrives()`
- L207 `test_r1_due_session_stop_is_competing_not_retroactive_owner()`
- L222 `test_r1_candidate_due_on_boundary_is_observed_but_boundary_owns()`
- L248 `test_r1_blocked_boundary_sell_retries_past_boundary_until_fill()`
- L279 `test_r1_next_event_boundary_keeps_owner_and_specific_reason_separate()`
- L295 `test_r1_preserves_entry_provenance_under_r1_revision_keys()`
- L320 `test_r1_suspension_does_not_start_or_reset_watch()`
- L336 `test_r1_candidate_disabled_control_matches_direct_v10_business_fields()`
- L374 `test_r1_event_closure_carries_flat_cash_and_unfilled_budget()`
- L426 `test_r1_integrity_rejects_targeted_ledger_corruption(mutation, message)`
- L452 `test_r1_declared_output_comparison_checks_missing_and_changed_files()`

## tests/test_v13_forward_marker.py

[打开文件](../../tests/test_v13_forward_marker.py)

- L19 `test_v13_scope_is_marker_only_and_non_writing()`
- L31 `test_v13_preflight_reads_no_returns_and_writes_nothing()`
- L40 `test_v13_execution_request_fails_closed(capsys)`
- L50 `test_v13_scope_rejects_string_boolean_authority()`
- L59 `test_v13_scope_rejects_execution_and_output_authority()`
- L73 `test_v13_scope_rejects_sector_or_output_schema_drift()`
- L86 `test_v13_forward_boundary_and_frame_validation()`
- L100 `test_v13_safe_output_rejects_historical_roots()`

## tests/test_v4_config_validation.py

[打开文件](../../tests/test_v4_config_validation.py)

- L29 `v4_config()`
- L38 `v4_factors(v4_config)`
- L47 `test_v4_config_marks_log_market_cap_as_neutralizer(v4_factors)`
- L57 `test_v4_config_all_factors_have_required_fields(v4_factors)`
- L69 `test_v4_config_has_required_gate_sections(v4_config)`
- L76 `test_v4_config_gate_basis_has_required_fields(v4_config)`
- L87 `test_v4_config_robustness_has_windows(v4_config)`
- L104 `test_v4_config_capacity_enabled(v4_config)`
- L112 `test_v4_config_valuation_factors_are_pit_aligned_zero_lag(v4_factors)`
- L127 `test_v4_config_quarterly_fundamentals_are_pit_aligned(v4_factors)`
- L137 `test_v4_config_technical_factors_have_zero_lag(v4_factors)`
- L149 `test_empty_rolling_window_csv_has_header()`
- L165 `test_empty_capacity_csv_has_header()`
- L179 `test_empty_correlation_cluster_csv_has_header()`
- L193 `test_non_empty_csv_writes_correctly()`
- L219 `test_candidate_pool_neutralizer_contract()`
- L246 `test_candidate_pool_with_eligible()`
- L268 `test_validate_csvs_readable_header_only()`
- L293 `test_validate_candidate_pool_with_config()`
- L322 `test_validate_candidate_pool_catches_neutralizer_in_eligible()`
- L349 `test_v4_rolling_windows_use_start_end_schema(v4_config)`
- L371 `test_v4_rolling_windows_match_script_contract()`
- L397 `test_validate_robustness_config_rejects_old_schema()`
- L412 `test_validate_robustness_config_rejects_bad_date()`
- L426 `test_validate_robustness_config_accepts_valid_schema()`
- L441 `test_validate_robustness_config_accepts_empty_windows()`

## tests/test_validate_validation_manifest.py

[打开文件](../../tests/test_validate_validation_manifest.py)

- L42 `class TestSHA256`
- L45 `TestSHA256.test_sha256_hex_deterministic(self)`
- L57 `TestSHA256.test_sha256_different_content(self)`
- L71 `class TestYearCoverage`
- L74 `TestYearCoverage.test_all_years_present(self)`
- L79 `TestYearCoverage.test_missing_years(self)`
- L86 `TestYearCoverage.test_missing_only_ytd(self)`
- L95 `class TestReturnCodes`
- L98 `TestReturnCodes.test_all_zero(self)`
- L103 `TestReturnCodes.test_nonzero_found(self)`
- L110 `class TestStrategyUnique`
- L113 `TestStrategyUnique.test_single_strategy(self)`
- L118 `TestStrategyUnique.test_multiple_strategies(self)`
- L124 `TestStrategyUnique.test_empty_strategies(self)`
- L130 `class TestManifestValidation`
- L133 `TestManifestValidation.setup_method(self)`
- L136 `TestManifestValidation.teardown_method(self)`
- L140 `TestManifestValidation._make_run_dir(self, year: str, factors_hash: str, regime_hash: str, factors_path: str='configs/factors_candidate_v4_r2.yaml', regime_path: str='configs/regime_candidate_v4_r2.yaml')`
- L164 `TestManifestValidation.test_all_manifests_match(self)`
- L183 `TestManifestValidation.test_hash_mismatch_detected(self)`
- L200 `TestManifestValidation.test_missing_manifest(self)`
- L217 `TestManifestValidation.test_nonexistent_run_dir(self)`
- L229 `TestManifestValidation.test_config_path_differs(self)`
- L249 `class TestIntegration`
- L252 `TestIntegration.test_script_imports_cleanly(self)`
- L257 `TestIntegration.test_help_flag(self, capsys)`
- L264 `class TestManifestMismatchCount`
- L267 `TestManifestMismatchCount.test_mismatch_count_zero_on_match(self)`

## tests/test_validation_firewall_registry.py

[打开文件](../../tests/test_validation_firewall_registry.py)

- L12 `_split(name: str, year: int)`
- L21 `test_two_preconstructed_registries_do_not_lose_entries(tmp_path)`
- L37 `test_concurrent_same_candidate_merges_new_validation_years(tmp_path)`
- L53 `test_new_candidate_has_all_years_untested(tmp_path)`
- L58 `test_oos_split_claim_is_atomic_and_durable(tmp_path)`
- L82 `test_register_replaces_persisted_claim_with_result(tmp_path)`
- L102 `test_evaluator_output_directory_has_one_run_owner(tmp_path)`
- L112 `test_v1_registry_is_read_and_migrated_on_commit(tmp_path)`
- L136 `test_corrupt_registry_contract_fails_closed(tmp_path, mutation)`
- L163 `test_malformed_registry_lock_fails_immediately(tmp_path)`
- L177 `test_duplicate_year_claim_is_rejected(tmp_path)`
- L190 `test_rejected_candidate_cannot_be_upgraded_by_later_partial_run(tmp_path)`

## tests/test_vehicle_compare.py

[打开文件](../../tests/test_vehicle_compare.py)

- L25 `test_mapping_freeze_does_not_use_semiconductor_as_electronics()`
- L40 `test_identical_prices_make_all_spreads_zero()`
- L64 `test_compare_hold_windows_nav_impl_and_main_board()`
- L98 `test_period_return_requires_both_dates()`
- L103 `test_etf_open_path_is_split_safe_and_timing_is_separate()`
- L138 `test_hold_period_coverage_requires_both_ends()`
- L152 `test_period_return_nan_in_chain_blocks_not_dropped()`
- L161 `test_open_nan_does_not_fallback_to_close()`
- L189 `test_period_return_expected_dates_must_match()`
- L202 `test_empty_expected_dates_blocks_two_point_chain()`
- L213 `test_calendar_unverified_is_data_insufficient(monkeypatch)`
- L231 `test_vehicle_integrity_blocks_etf_nan_even_if_stock_coverage_ok()`
- L267 `test_etf_preclose_ignores_share_split_jump()`

## tests/test_verify_golden.py

[打开文件](../../tests/test_verify_golden.py)

- L36 `_fake_git_run(args, **kwargs)`
- L69 `_write_file(root: Path, rel: str, content: str='x')`
- L76 `_sha(rel: str, root: Path)`
- L81 `env(tmp_path, monkeypatch)`
- L162 `class TestVerifyGolden`
- L163 `TestVerifyGolden.test_intact_baseline_passes(self, env)`
- L167 `TestVerifyGolden.test_tampered_source_file_detected(self, env)`
- L173 `TestVerifyGolden.test_tampered_untracked_file_detected(self, env)`
- L181 `TestVerifyGolden.test_unpinned_untracked_file_detected(self, env, monkeypatch)`
- L202 `TestVerifyGolden.test_unpinned_tracked_source_file_detected(self, env, monkeypatch)`
- L227 `TestVerifyGolden.test_dirty_diff_hash_drift_detected(self, env)`
- L233 `TestVerifyGolden.test_dirty_file_list_drift_detected(self, env, monkeypatch)`
- L251 `TestVerifyGolden.test_contract_file_drift_detected(self, env)`
- L258 `TestVerifyGolden.test_output_artifact_drift_detected(self, env)`
- L267 `TestVerifyGolden.test_dynamic_shadow_artifact_drift_is_not_golden_drift(self, env)`
- L277 `TestVerifyGolden.test_head_movement_with_committed_source_is_detected(self, env, monkeypatch)`
- L289 `TestVerifyGolden.test_baseline_only_amend_commit_is_allowed(self, env, monkeypatch)`
- L312 `TestVerifyGolden.test_uncommitted_baseline_file_detected(self, env, monkeypatch)`
- L327 `class TestAmendBaseline`
- L328 `TestAmendBaseline.test_amend_rewrites_hashes_and_git_state(self, env, tmp_path)`
- L359 `TestAmendBaseline.test_amend_missing_baseline_raises(self, tmp_path)`
- L364 `TestAmendBaseline.test_amend_rejects_vague_reason(self, env, tmp_path)`

## tests/test_volume_enhancement.py

[打开文件](../../tests/test_volume_enhancement.py)

- L44 `_make_prices(n_days: int=100, seed: int=42)`
- L61 `_make_daily_basic(n_days: int=100, seed: int=42)`
- L80 `class TestVolumeFeatures`
- L81 `TestVolumeFeatures.test_default_fields_are_nan(self)`
- L86 `TestVolumeFeatures.test_columns_method_returns_all_fields(self)`
- L96 `class TestRollingHelpers`
- L97 `TestRollingHelpers.test_rolling_median_ratio_excludes_current(self)`
- L107 `TestRollingHelpers.test_robust_zscore_produces_finite_values(self)`
- L112 `TestRollingHelpers.test_amihud_illiquidity_positive(self)`
- L119 `TestRollingHelpers.test_down_amount_share_between_zero_and_one(self)`
- L130 `class TestBasketAggregation`
- L131 `TestBasketAggregation.test_median_returns_nan_on_empty(self)`
- L134 `TestBasketAggregation.test_median_ignores_nan(self)`
- L137 `TestBasketAggregation.test_fraction_returns_nan_on_empty(self)`
- L140 `TestBasketAggregation.test_fraction_computes_correctly(self)`
- L143 `TestBasketAggregation.test_dispersion_returns_nan_on_small_sample(self)`
- L151 `class TestComputeVolumeFeatures`
- L152 `TestComputeVolumeFeatures.test_returns_empty_features_for_no_components(self)`
- L156 `TestComputeVolumeFeatures.test_returns_coverage_metrics_with_prices(self)`
- L168 `TestComputeVolumeFeatures.test_marks_turnover_unavailable_when_daily_basic_is_none(self)`
- L177 `TestComputeVolumeFeatures.test_low_coverage_invalidates_all_basket_aggregates(self)`
- L202 `TestComputeVolumeFeatures.test_does_not_modify_prices_dataframe(self)`
- L221 `class TestValidationFirewall`
- L222 `TestValidationFirewall.test_split_seals_after_validate(self)`
- L234 `TestValidationFirewall.test_sealed_split_cannot_change_threshold(self)`
- L245 `TestValidationFirewall.test_firewall_records_rejections(self)`
- L257 `TestValidationFirewall.test_firewall_counts_pass_as_tested(self)`
- L262 `TestValidationFirewall.test_expanding_window_split_produces_splits(self)`
- L275 `TestValidationFirewall.test_leave_one_year_out_skips_small_folds(self)`
- L290 `class TestHardGateChecker`
- L291 `TestHardGateChecker.test_all_gates_pass_for_trivial_candidate(self)`
- L330 `TestHardGateChecker.test_median_worse_fails(self)`
- L335 `TestHardGateChecker.test_multiple_candidates_fails(self)`
- L341 `TestHardGateChecker.test_top3_dominant_fails(self)`
- L351 `TestHardGateChecker.test_jackknife_unstable_fails(self)`
- L359 `TestHardGateChecker.test_cost_100bp_no_improvement_fails(self)`
- L367 `TestHardGateChecker.test_result_has_audit_trail(self)`
- L381 `TestHardGateChecker.test_diagnostic_only_requires_two_independent_snapshots(self)`

## tests/test_weekly_long_holding.py

[打开文件](../../tests/test_weekly_long_holding.py)

- L33 `_dates(n: int)`
- L37 `_one_asset_panel(n: int=17, daily_ret: float=0.01)`
- L48 `test_hold_windows_span_to_next_event_not_next_day()`
- L59 `test_synthetic_index_weekly_compounds_full_hold()`
- L73 `test_synthetic_etf_t1_matches_eleven_day_hold()`
- L85 `test_ir_ann_factor_is_weekly_not_sqrt252()`
- L99 `test_annualization_factor_daily_near_252()`
- L105 `test_drift_holdings_rebalance_turnover_after_double()`
- L116 `test_drift_holdings_keeps_cash_when_prices_flat()`
- L125 `test_mark_holdings_suspend_is_not_unexplained_gap()`
- L136 `test_mark_holdings_catches_up_after_missing_quote()`
- L151 `test_etf_full_rotate_cash_covers_4bp()`
- L167 `test_apply_cost_from_cash_does_not_haircut_stock()`
- L176 `test_data_insufficient_blocks_go()`
- L184 `test_drift_holdings_keeps_missing_price_name()`
- L194 `test_adjusted_fill_captures_open_to_next_open()`
- L212 `test_annual_return_includes_first_nav_leg()`
- L219 `test_index_weekly_post_trade_weights_exclude_future_mark()`
- L241 `test_index_weekly_catches_up_missing_quote()`
- L265 `test_unknown_limit_counts_existing_holding_on_exit()`
- L274 `test_unknown_limit_excludes_suspended_holding()`
- L284 `test_gap_counts_missing_initial_valuation()`
- L292 `test_industry_universe_keeps_only_shenwan_l1()`

## validation/__init__.py

[打开文件](../../validation/__init__.py)

无顶层函数/类；阅读模块常量、导入或入口逻辑。

## validation/diagnostics.py

[打开文件](../../validation/diagnostics.py)

- L34 `_safe_float(val, default=float('nan'))`
- L42 `_is_oos(date_val, oos_start=OOS_START_DATE)`
- L57 `decompose_turnover(trades_log: List[Dict], holdings_log: List[Dict], portfolio_values: List[Dict])`
- L158 `_build_trade_df(trades_log: List[Dict])`
- L169 `_estimate_turnover_components(holdings_log: List[Dict], trades_log: List[Dict])`
- L224 `_weekly_monthly_comparison(trade_df: pd.DataFrame)`
- L258 `decompose_costs(portfolio_values: List[Dict], cost_multipliers: Optional[List[float]]=None)`
- L423 `analyze_fallback(opt_diagnostics: Dict[str, Any], trades_log: Optional[List[Dict]]=None)`
- L504 `_classify_fallback_reasons(raw_reasons: Dict[str, int])`
- L529 `build_fallback_events_csv(opt_diagnostics: Dict[str, Any], trades_log: Optional[List[Dict]]=None, holdings_log: Optional[List[Dict]]=None)`
- L585 `analyze_factor_stability(factor_dfs: Dict[str, pd.DataFrame], fwd_rets: pd.DataFrame, signal_dates: List[int], ic_weighting=None)`
- L675 `_compute_annual_ic(factor_df: pd.DataFrame, fwd_rets: pd.DataFrame, signal_dates: List[int], horizon_col: str)`
- L741 `_compute_coverage_stats(factor_df: pd.DataFrame, signal_dates: List[int])`
- L770 `_check_2025_decay(factor_df: pd.DataFrame, fwd_rets: pd.DataFrame, signal_dates: List[int], horizon_col: str)`
- L800 `_compute_period_ic(factor_df, fwd_rets, dates, horizon_col)`
- L821 `_estimate_factor_turnover_contribution(factor_df: pd.DataFrame, signal_dates: List[int])`
- L881 `_identify_cost_sensitive_factors(factor_turnover_beta: Dict[str, Any], annual_ic: Dict[str, Any])`
- L920 `class Phase5Diagnostics`
- L944 `Phase5Diagnostics.__init__(self, backtest_result: Dict[str, Any], opt_diagnostics: Optional[Dict[str, Any]]=None, trades_log: Optional[List[Dict]]=None, holdings_log: Optional[List[Dict]]=None, portfolio_values: Optional[List[Dict]]=None, factor_dfs: Optional[Dict[str, pd.DataFrame]]=None, fwd_rets: Optional[pd.DataFrame]=None, signal_dates: Optional[List[int]]=None)`
- L972 `Phase5Diagnostics.run_all(self)`
- L993 `Phase5Diagnostics.generate_report(self)`
- L1064 `Phase5Diagnostics._append_turnover_section(self, lines, to)`
- L1098 `Phase5Diagnostics._append_cost_section(self, lines, cost)`
- L1133 `Phase5Diagnostics._append_fallback_section(self, lines, fb)`
- L1160 `Phase5Diagnostics._append_factor_section(self, lines, fs)`
- L1227 `Phase5Diagnostics.to_json(self, path: Optional[Path]=None)`
- L1252 `Phase5Diagnostics.export_fallback_csv(self, path: Optional[Path]=None)`
- L1265 `Phase5Diagnostics.export_turnover_csv(self, path: Optional[Path]=None)`
- L1299 `_fmt_val(val, fmt: str)`
- L1313 `_fmt_pct(val)`
- L1323 `_make_json_safe(obj: Any)`

## validation/experiment_runner.py

[打开文件](../../validation/experiment_runner.py)

- L63 `class ExperimentRunner`
- L75 `ExperimentRunner.__init__(self, config_path: str='configs/phase5_experiments.yaml', args: Any=None)`
- L111 `ExperimentRunner._load_config(self)`
- L137 `ExperimentRunner.build_grid(self, experiment_name: str)`
- L186 `ExperimentRunner._selection_interval(self, config: Dict[str, Any])`
- L215 `ExperimentRunner._build_bt_kwargs(self, config: Dict[str, Any], composite: pd.DataFrame, mu_df: Optional[pd.DataFrame])`
- L241 `ExperimentRunner.run(self)`
- L282 `ExperimentRunner._evaluate_config(self, config: Dict[str, Any], label: str)`
- L415 `ExperimentRunner._filter_candidates(self, results: List[Dict])`
- L483 `ExperimentRunner._cap_per_line(self, candidates: List[Dict])`
- L513 `ExperimentRunner._one_day_before(date_str: str)`
- L525 `ExperimentRunner._write_outputs(self)`
- L550 `ExperimentRunner._generate_report(self)`
- L646 `ExperimentRunner._make_label(self, exp_name: str, config: Dict[str, Any], index: int)`
- L663 `_fmt(val, fmt_str: str)`
- L675 `_safe_num(val, default: float=0.0)`

## validation/robustness.py

[打开文件](../../validation/robustness.py)

- L32 `_safe_fmt(val, fmt: str)`
- L46 `class RobustnessTester`
- L51 `RobustnessTester.__init__(self, backtest_fn: Callable[..., Dict[str, Any]])`
- L65 `RobustnessTester.test_cost_sensitivity(self, base_config: dict)`
- L78 `RobustnessTester.test_slippage_sensitivity(self, base_config: dict)`
- L91 `RobustnessTester.test_rebalance_frequency(self, base_config: dict, frequencies: Optional[List[tuple]]=None)`
- L117 `RobustnessTester.test_portfolio_size(self, base_config: dict)`
- L130 `RobustnessTester.test_stock_caps(self, base_config: dict)`
- L143 `RobustnessTester.test_industry_deviation(self, base_config: dict)`
- L157 `RobustnessTester.test_market_regimes(self, base_config: dict, regimes: Optional[List[Tuple[str, str, str]]]=None)`
- L213 `RobustnessTester.test_turnover_scenarios(self, base_config: dict)`
- L263 `RobustnessTester.test_parameter_sensitivity(self, base_config: dict, param_name: str, param_values: List[Any])`
- L289 `RobustnessTester.go_nogo_check(self, base_result: Dict[str, Any], cost_2x_result: Optional[Dict[str, Any]]=None, recent_oos_result: Optional[Dict[str, Any]]=None, ir_threshold: float=0.3, max_dd_threshold: float=0.25, min_excess_return: float=0.03, min_oos_excess: float=0.02, max_turnover: float=0.3)`
- L651 `RobustnessTester.generate_report(self)`
- L796 `RobustnessTester.compute_rolling_window_metrics(returns: pd.Series, window: int=52, metric_fn: Callable=np.mean)`
- L804 `RobustnessTester.compute_rolling_ir(strategy_returns: pd.Series, benchmark_returns: pd.Series, window: int=52)`
- L814 `RobustnessTester.compute_rolling_sharpe(returns: pd.Series, window: int=52)`

## validation/sample_windows.py

[打开文件](../../validation/sample_windows.py)

- L17 `class ResearchIdentity`
- L36 `classify_window(start: int, end: int)`
- L46 `may_claim_oos(start: int, end: int, *, identity: ResearchIdentity=DEFAULT_IDENTITY)`
- L63 `may_approve_live(identity: ResearchIdentity=DEFAULT_IDENTITY)`
- L67 `assert_not_live_authority(start: int, end: int, *, identity: ResearchIdentity=DEFAULT_IDENTITY)`

## validation/walk_forward.py

[打开文件](../../validation/walk_forward.py)

- L23 `class WalkForwardValidator`
- L32 `WalkForwardValidator.__init__(self, n_initial_train: int=252, n_test: int=21, n_retrain: int=63, purge_days: int=5, embargo_days: int=60, expanding_window: bool=True, rolling_window_size: Optional[int]=None)`
- L51 `WalkForwardValidator.generate_splits(self, dates: List[int])`
- L120 `WalkForwardValidator.run(self, dates: List[int], train_fn: Callable[[List[int]], Any], test_fn: Callable[[Any, List[int]], Dict[str, float]])`
- L182 `WalkForwardValidator.summarize(results: List[Dict[str, Any]], metric_keys: Optional[List[str]]=None)`
- L233 `WalkForwardValidator.stability_report(results: List[Dict[str, Any]], ic_key: str='rank_ic')`

## 配置文件导航

配置存在不代表某次运行启用；从入口参数和 manifest 回查。

- [configs/costs.yaml](../../configs/costs.yaml)
- [configs/data.yaml](../../configs/data.yaml)
- [configs/direct_state_v1.yaml](../../configs/direct_state_v1.yaml)
- [configs/factor_build_v4.yaml](../../configs/factor_build_v4.yaml)
- [configs/factor_panic_reversal_build.yaml](../../configs/factor_panic_reversal_build.yaml)
- [configs/factor_quality_rebuild.yaml](../../configs/factor_quality_rebuild.yaml)
- [configs/factor_quality_rebuild_v4.yaml](../../configs/factor_quality_rebuild_v4.yaml)
- [configs/factors.yaml](../../configs/factors.yaml)
- [configs/factors_5reversal.yaml](../../configs/factors_5reversal.yaml)
- [configs/factors_alpha_v4_universe.yaml](../../configs/factors_alpha_v4_universe.yaml)
- [configs/factors_candidate_v1.yaml](../../configs/factors_candidate_v1.yaml)
- [configs/factors_candidate_v4.yaml](../../configs/factors_candidate_v4.yaml)
- [configs/factors_candidate_v4_r1.yaml](../../configs/factors_candidate_v4_r1.yaml)
- [configs/factors_candidate_v4_r2.yaml](../../configs/factors_candidate_v4_r2.yaml)
- [configs/factors_dynamic.yaml](../../configs/factors_dynamic.yaml)
- [configs/factors_panic_reversal_universe.yaml](../../configs/factors_panic_reversal_universe.yaml)
- [configs/factors_shock_reversal.yaml](../../configs/factors_shock_reversal.yaml)
- [configs/optimizer.yaml](../../configs/optimizer.yaml)
- [configs/phase5_experiments.yaml](../../configs/phase5_experiments.yaml)
- [configs/photoresist_basket_constraints_v2_candidate.yaml](../../configs/photoresist_basket_constraints_v2_candidate.yaml)
- [configs/photoresist_panic_live.yaml](../../configs/photoresist_panic_live.yaml)
- [configs/photoresist_panic_monitor.yaml](../../configs/photoresist_panic_monitor.yaml)
- [configs/photoresist_panic_research.yaml](../../configs/photoresist_panic_research.yaml)
- [configs/photoresist_panic_shadow_gate_contract.json](../../configs/photoresist_panic_shadow_gate_contract.json)
- [configs/photoresist_universe.yaml](../../configs/photoresist_universe.yaml)
- [configs/photoresist_universe_v2.yaml](../../configs/photoresist_universe_v2.yaml)
- [configs/regime.yaml](../../configs/regime.yaml)
- [configs/regime_candidate_v1.yaml](../../configs/regime_candidate_v1.yaml)
- [configs/regime_candidate_v2.yaml](../../configs/regime_candidate_v2.yaml)
- [configs/regime_candidate_v3.yaml](../../configs/regime_candidate_v3.yaml)
- [configs/regime_candidate_v4.yaml](../../configs/regime_candidate_v4.yaml)
- [configs/regime_candidate_v4_r1.yaml](../../configs/regime_candidate_v4_r1.yaml)
- [configs/regime_candidate_v4_r2.yaml](../../configs/regime_candidate_v4_r2.yaml)
- [configs/regime_shock_reversal.yaml](../../configs/regime_shock_reversal.yaml)
- [configs/regime_v2.yaml](../../configs/regime_v2.yaml)
- [configs/sample_windows_v1.yaml](../../configs/sample_windows_v1.yaml)
- [configs/sector_panic/component_avwap_hwm_historical_scope_v1.yaml](../../configs/sector_panic/component_avwap_hwm_historical_scope_v1.yaml)
- [configs/sector_panic/component_avwap_loss_audit_scope_v1.yaml](../../configs/sector_panic/component_avwap_loss_audit_scope_v1.yaml)
- [configs/sector_panic/component_avwap_scope_v1.yaml](../../configs/sector_panic/component_avwap_scope_v1.yaml)
- [configs/sector_panic/component_entry_avwap_gate_scope_v1.yaml](../../configs/sector_panic/component_entry_avwap_gate_scope_v1.yaml)
- [configs/sector_panic/component_exit_scope_v1.yaml](../../configs/sector_panic/component_exit_scope_v1.yaml)
- [configs/sector_panic/component_natr_stop_cause_presentation_scope_v1.yaml](../../configs/sector_panic/component_natr_stop_cause_presentation_scope_v1.yaml)
- [configs/sector_panic/component_natr_stop_exploratory_scope_v1.yaml](../../configs/sector_panic/component_natr_stop_exploratory_scope_v1.yaml)
- [configs/sector_panic/component_natr_stop_presentation_scope_v1.yaml](../../configs/sector_panic/component_natr_stop_presentation_scope_v1.yaml)
- [configs/sector_panic/component_natr_stop_trade_timing_presentation_scope_v1.yaml](../../configs/sector_panic/component_natr_stop_trade_timing_presentation_scope_v1.yaml)
- [configs/sector_panic/component_repair_confirmation_exploratory_scope_v1.yaml](../../configs/sector_panic/component_repair_confirmation_exploratory_scope_v1.yaml)
- [configs/sector_panic/component_repair_quality_v2_exploratory_scope_r1.yaml](../../configs/sector_panic/component_repair_quality_v2_exploratory_scope_r1.yaml)
- [configs/sector_panic/component_repair_quality_v2_exploratory_scope_r2.yaml](../../configs/sector_panic/component_repair_quality_v2_exploratory_scope_r2.yaml)
- [configs/sector_panic/component_repair_quality_v2_exploratory_scope_r3.yaml](../../configs/sector_panic/component_repair_quality_v2_exploratory_scope_r3.yaml)
- [configs/sector_panic/component_repair_quality_v2_exploratory_scope_r4.yaml](../../configs/sector_panic/component_repair_quality_v2_exploratory_scope_r4.yaml)
- [configs/sector_panic/component_repair_quality_v2_exploratory_scope_r5.yaml](../../configs/sector_panic/component_repair_quality_v2_exploratory_scope_r5.yaml)
- [configs/sector_panic/component_repair_quality_v2_exploratory_scope_r6.yaml](../../configs/sector_panic/component_repair_quality_v2_exploratory_scope_r6.yaml)
- [configs/sector_panic/component_repair_quality_v2_exploratory_scope_r7.yaml](../../configs/sector_panic/component_repair_quality_v2_exploratory_scope_r7.yaml)
- [configs/sector_panic/component_repair_quality_v2_exploratory_scope_v1.yaml](../../configs/sector_panic/component_repair_quality_v2_exploratory_scope_v1.yaml)
- [configs/sector_panic/component_repair_quality_v2_report_scope_r7.yaml](../../configs/sector_panic/component_repair_quality_v2_report_scope_r7.yaml)
- [configs/sector_panic/component_repair_quality_v2_report_scope_r8.yaml](../../configs/sector_panic/component_repair_quality_v2_report_scope_r8.yaml)
- [configs/sector_panic/component_repair_quality_v2_report_scope_r9.yaml](../../configs/sector_panic/component_repair_quality_v2_report_scope_r9.yaml)
- [configs/sector_panic/confirmation_close_reentry_v10_scope.yaml](../../configs/sector_panic/confirmation_close_reentry_v10_scope.yaml)
- [configs/sector_panic/confirmation_invalidation_v11_scope.yaml](../../configs/sector_panic/confirmation_invalidation_v11_scope.yaml)
- [configs/sector_panic/entry_confirmation_r0_collector_implementation_v1.yaml](../../configs/sector_panic/entry_confirmation_r0_collector_implementation_v1.yaml)
- [configs/sector_panic/entry_confirmation_r0_forward_scope_v1.yaml](../../configs/sector_panic/entry_confirmation_r0_forward_scope_v1.yaml)
- [configs/sector_panic/entry_exit_attribution_matrix_scope.yaml](../../configs/sector_panic/entry_exit_attribution_matrix_scope.yaml)
- [configs/sector_panic/entry_review_buffer_v9_scope.yaml](../../configs/sector_panic/entry_review_buffer_v9_scope.yaml)
- [configs/sector_panic/extension_no_chase_structural_failure_v8_report_scope_r1.yaml](../../configs/sector_panic/extension_no_chase_structural_failure_v8_report_scope_r1.yaml)
- [configs/sector_panic/extension_no_chase_structural_failure_v8_scope.yaml](../../configs/sector_panic/extension_no_chase_structural_failure_v8_scope.yaml)
- [configs/sector_panic/lithium_battery.yaml](../../configs/sector_panic/lithium_battery.yaml)
- [configs/sector_panic/lithium_mining_universe_template.yaml](../../configs/sector_panic/lithium_mining_universe_template.yaml)
- [configs/sector_panic/new_energy.yaml](../../configs/sector_panic/new_energy.yaml)
- [configs/sector_panic/nonferrous.yaml](../../configs/sector_panic/nonferrous.yaml)
- [configs/sector_panic/p1_loss_diagnostic_v1.yaml](../../configs/sector_panic/p1_loss_diagnostic_v1.yaml)
- [configs/sector_panic/phase1_execution_scope_v1.yaml](../../configs/sector_panic/phase1_execution_scope_v1.yaml)
- [configs/sector_panic/portfolio_economic_contract_v1.yaml](../../configs/sector_panic/portfolio_economic_contract_v1.yaml)
- [configs/sector_panic/portfolio_economic_contract_v1_freeze.json](../../configs/sector_panic/portfolio_economic_contract_v1_freeze.json)
- [configs/sector_panic/rebuild_e2_fill_sample_contract_v1.yaml](../../configs/sector_panic/rebuild_e2_fill_sample_contract_v1.yaml)
- [configs/sector_panic/rebuild_e2_full214_engineering_contract_v1.yaml](../../configs/sector_panic/rebuild_e2_full214_engineering_contract_v1.yaml)
- [configs/sector_panic/rebuild_e2_risk_contract_v1.yaml](../../configs/sector_panic/rebuild_e2_risk_contract_v1.yaml)
- [configs/sector_panic/rebuild_v1_diagnostic_contract.yaml](../../configs/sector_panic/rebuild_v1_diagnostic_contract.yaml)
- [configs/sector_panic/rebuild_v1_diagnostic_sample.json](../../configs/sector_panic/rebuild_v1_diagnostic_sample.json)
- [configs/sector_panic/rebuild_v1_scope.yaml](../../configs/sector_panic/rebuild_v1_scope.yaml)
- [configs/sector_panic/research_scope_r7_v20260815.yaml](../../configs/sector_panic/research_scope_r7_v20260815.yaml)
- [configs/sector_panic/research_scope_v2.yaml](../../configs/sector_panic/research_scope_v2.yaml)
- [configs/sector_panic/research_scope_v3.yaml](../../configs/sector_panic/research_scope_v3.yaml)
- [configs/sector_panic/sector_admission_register.yaml](../../configs/sector_panic/sector_admission_register.yaml)
- [configs/sector_panic/t0_cluster_duration_predictor_scope_v1.yaml](../../configs/sector_panic/t0_cluster_duration_predictor_scope_v1.yaml)
- [configs/sector_panic/t0_mechanism_quintiles_scope_v1.yaml](../../configs/sector_panic/t0_mechanism_quintiles_scope_v1.yaml)
- [configs/sector_panic/v10_delayed_structure_path_check_scope.yaml](../../configs/sector_panic/v10_delayed_structure_path_check_scope.yaml)
- [configs/sector_panic/v10_h1_mech_half_scope.yaml](../../configs/sector_panic/v10_h1_mech_half_scope.yaml)
- [configs/sector_panic/v10_max_hold_path_diagnostic_scope.yaml](../../configs/sector_panic/v10_max_hold_path_diagnostic_scope.yaml)
- [configs/sector_panic/v10_selective_exit_action_value_r1_scope.yaml](../../configs/sector_panic/v10_selective_exit_action_value_r1_scope.yaml)
- [configs/sector_panic/v10_selective_exit_action_value_r1_scope_engfix_r1.yaml](../../configs/sector_panic/v10_selective_exit_action_value_r1_scope_engfix_r1.yaml)
- [configs/sector_panic/v10_selective_exit_action_value_r1_scope_engfix_r2.yaml](../../configs/sector_panic/v10_selective_exit_action_value_r1_scope_engfix_r2.yaml)
- [configs/sector_panic/v12_evidence_stack_engine_r1_defectfix_scope.yaml](../../configs/sector_panic/v12_evidence_stack_engine_r1_defectfix_scope.yaml)
- [configs/sector_panic/v12_evidence_stack_engine_scope.yaml](../../configs/sector_panic/v12_evidence_stack_engine_scope.yaml)
- [configs/sector_panic/v12_evidence_stack_scope.yaml](../../configs/sector_panic/v12_evidence_stack_scope.yaml)
- [configs/sector_panic/v13_forward_scope.yaml](../../configs/sector_panic/v13_forward_scope.yaml)
- [configs/sector_panic/v14_confirmation_floor_epsilon_forward_scope.yaml](../../configs/sector_panic/v14_confirmation_floor_epsilon_forward_scope.yaml)
- [configs/strategy_v1_candidate_pool.yaml](../../configs/strategy_v1_candidate_pool.yaml)
- [configs/vehicle_compare_v1.yaml](../../configs/vehicle_compare_v1.yaml)

"""
Portfolio-level backtester for CSI 300 cross-sectional strategy.

MVP features:
- Top N equal-weight or IC-weighted selection
- T+1 execution (signal at t, trade at t+1 open)
- Weekly rebalance
- Tradable mask filtering (suspension, limit up/down, ST)
- Weight freezing for untradable positions
- Explicit + implicit transaction costs
- Benchmark vs CSI 300 index and equal-weight CSI 300 constituents

Phase 2 deliverable: top-quantile equal-weight portfolio backtest.
Phase 3 will add mean-variance optimization.

Memory: streams rebalance date by date. Never constructs full
(date x stock x weights x prices) tensor.
"""

import logging
from typing import Optional, List, Dict, Any, Tuple
from copy import deepcopy
from datetime import datetime

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class PortfolioBacktester:
    """
    T+1 weekly rebalance portfolio backtester.

    Parameters
    ----------
    universe_builder : UniverseBuilder
        PIT universe provider.
    execution : ExecutionSimulator
        Trade execution simulator.
    cost_model : CostModel
        Transaction cost model.
    tradable : TradableMask
        Tradable mask generator.
    panel_loader : PanelLoader
        Data access layer.
    """

    def __init__(self,
                 universe_builder=None,
                 execution_simulator=None,
                 cost_model=None,
                 tradable_mask=None,
                 panel_loader=None,
                 config: Optional[dict] = None):
        self._universe = universe_builder
        self._execution = execution_simulator
        self._cost_model = cost_model
        self._tradable = tradable_mask
        self._loader = panel_loader
        self.config = config or {}
        from backtest.cost_model import CostConfig
        if cost_model is not None and getattr(cost_model, "config", None) is not None:
            self._base_cost_config = deepcopy(cost_model.config)
        else:
            self._base_cost_config = CostConfig()

    @property
    def universe(self):
        if self._universe is None:
            from data.universe import get_universe_builder
            self._universe = get_universe_builder()
        return self._universe

    @property
    def execution(self):
        if self._execution is None:
            from backtest.execution import ExecutionSimulator
            self._execution = ExecutionSimulator()
        return self._execution

    @property
    def cost_model(self):
        if self._cost_model is None:
            from backtest.cost_model import CostModel
            self._cost_model = CostModel()
        return self._cost_model

    @property
    def tradable(self):
        if self._tradable is None:
            from data.tradable import get_tradable
            self._tradable = get_tradable()
        return self._tradable

    @property
    def loader(self):
        if self._loader is None:
            from data.panel_loader import get_loader
            self._loader = get_loader()
        return self._loader

    # ------------------------------------------------------------------
    # Main backtest entry point
    # ------------------------------------------------------------------
    def run_backtest(self,
                     scores: pd.DataFrame,
                     score_col: str = "composite_score",
                     start_date: str = "20160101",
                     end_date: Optional[str] = None,
                     top_n: int = 50,
                     weighting: str = "equal",  # "equal", "score", or "optimized"
                     rebalance_freq: str = "weekly",
                     initial_capital: float = 100_000_000.0,
                     benchmark_code: str = "000300.SH",
                     cost_multiplier: float = 1.0,
                     slippage_bps: Optional[float] = None,
                     weight_max: float = 0.02,
                     mu_df: Optional[pd.DataFrame] = None,
                     entry_rank: Optional[int] = None,
                     exit_rank: Optional[int] = None,
                     turnover_max: Optional[float] = None,
                     turnover_penalty: Optional[float] = None,
                     no_trade_band: float = 0.0,
                     max_weight_change: Optional[float] = None,
                     score_smoothing_halflife: Optional[int] = None,
                     hold_buffer_mode: str = "standard",
                     cost_aware_lambda: float = 0.0,
                     estimated_cost_bps: float = 10.0,
                     cov_shrinkage: str = "ledoit_wolf",
                     constraint_relaxation: str = "none",
                     return_diagnostics: bool = False,
                     ) -> Dict[str, Any]:
        """
        Run T+1 portfolio backtest.

        Parameters
        ----------
        scores : pd.DataFrame
            Composite scores with ts_code, trade_date, score_col.
        score_col : str
            Name of the score column to rank on.
        start_date, end_date : str
            Backtest date range YYYYMMDD.
        top_n : int
            Number of stocks in portfolio.
        weighting : str
            "equal" for equal weight, "score" for score-weighted.
        rebalance_freq : str
            "weekly" or "monthly".
        initial_capital : float
            Starting portfolio value in CNY.
        benchmark_code : str
            Benchmark index code.
        no_trade_band : float
            Minimum weight change to trigger trade (reduces micro-rebalancing).
        max_weight_change : float, optional
            Maximum individual stock weight change per rebalance.
        score_smoothing_halflife : int, optional
            Halflife (in periods) for exponential score smoothing.
        hold_buffer_mode : str
            Buffer mode: "standard" (entry_rank/exit_rank) or "aggressive".
        cost_aware_lambda : float
            Weight for explicit cost penalty in objective.
        estimated_cost_bps : float
            Estimated trading cost in bps for cost-aware term.
        cov_shrinkage : str
            Covariance estimation method override.
        constraint_relaxation : str
            Constraint relaxation strategy: "none" or "tiered".

        Returns
        -------
        dict with backtest results.
        """
        if end_date is None:
            end_date = datetime.now().strftime("%Y%m%d")

        logger.info(f"Running backtest: {start_date} -> {end_date}, "
                     f"top_n={top_n}, {weighting} weight, {rebalance_freq}"
                     f"{', cost_x' + str(cost_multiplier) if cost_multiplier != 1.0 else ''}")

        # Build a fresh per-run cost model so stress scenarios do not leak
        # into later backtests on the same PortfolioBacktester instance.
        from backtest.cost_model import CostModel
        from backtest.execution import ExecutionSimulator
        adj_config = deepcopy(self._base_cost_config)
        adj_config.commission_rate *= cost_multiplier
        adj_config.stamp_duty_rate *= cost_multiplier
        adj_config.transfer_fee_rate *= cost_multiplier
        if slippage_bps is not None:
            adj_config.slippage_bps = slippage_bps
        else:
            adj_config.slippage_bps *= cost_multiplier
        self._cost_model = CostModel(adj_config)
        self._execution = ExecutionSimulator(
            cost_model=self._cost_model,
            tradable_mask=self._tradable,
        )
        logger.debug(
            "Cost model configured: commission=%.5f, stamp=%.5f, "
            "transfer=%.5f, slippage=%.1fbps",
            adj_config.commission_rate,
            adj_config.stamp_duty_rate,
            adj_config.transfer_fee_rate,
            adj_config.slippage_bps,
        )

        # 1. Get signal/rebalance dates — explicitly load calendar to
        #    recover from any prior singleton pollution.
        from data.calendar import get_calendar
        cal = get_calendar()
        # Ensure calendar covers the backtest range (union semantics in load()
        # prevent shrinking; explicit call ensures self-recovery from pollution).
        cal.load(start_date=start_date, end_date=end_date)
        if rebalance_freq == "weekly":
            signal_dates = cal.weekly_rebalance_dates(start_date, end_date)
        elif rebalance_freq == "monthly":
            signal_dates = cal.monthly_rebalance_dates(start_date, end_date)
        else:
            raise ValueError(f"Unknown frequency: {rebalance_freq}")

        signal_dates_int = [int(d) for d in signal_dates]
        logger.info(f"Backtest: {len(signal_dates_int)} rebalance dates")

        if len(signal_dates_int) < 2:
            return {"error": "Insufficient rebalance dates"}

        # 2. Load benchmark returns
        benchmark_returns = self._load_benchmark_returns(
            benchmark_code, start_date, end_date
        )

        # 3. Run rebalance-by-rebalance simulation
        portfolio_values, holdings, trades_log, opt_diagnostics = self._simulate(
            scores, score_col, signal_dates_int,
            top_n, weighting, initial_capital, mu_df, weight_max,
            end_date=int(end_date),
            entry_rank=entry_rank, exit_rank=exit_rank,
            turnover_max=turnover_max, turnover_penalty=turnover_penalty,
            no_trade_band=no_trade_band,
            max_weight_change=max_weight_change,
            score_smoothing_halflife=score_smoothing_halflife,
            hold_buffer_mode=hold_buffer_mode,
            cost_aware_lambda=cost_aware_lambda,
            estimated_cost_bps=estimated_cost_bps,
            cov_shrinkage=cov_shrinkage,
            constraint_relaxation=constraint_relaxation,
        )

        # 4. Compute performance metrics
        results = self._compute_metrics(
            portfolio_values, benchmark_returns, holdings, trades_log,
            opt_diagnostics
        )

        results["config"] = {
            "start_date": start_date,
            "end_date": end_date,
            "top_n": top_n,
            "weighting": weighting,
            "rebalance_freq": rebalance_freq,
            "initial_capital": initial_capital,
            "n_rebalances": len(signal_dates_int),
            "weight_max": weight_max,
            "cost_multiplier": cost_multiplier,
            "slippage_bps": slippage_bps,
            "entry_rank": entry_rank,
            "exit_rank": exit_rank,
            "turnover_max": turnover_max,
            "turnover_penalty": turnover_penalty,
            "no_trade_band": no_trade_band,
            "max_weight_change": max_weight_change,
            "score_smoothing_halflife": score_smoothing_halflife,
            "cost_aware_lambda": cost_aware_lambda,
            "cov_shrinkage": cov_shrinkage,
            "constraint_relaxation": constraint_relaxation,
        }

        # Batch 3: Attach raw diagnostics payload when requested.
        # NOT included in _write_metrics_summary (key starts with _).
        if return_diagnostics:
            results["_diagnostics_payload"] = {
                "portfolio_values": portfolio_values,
                "holdings_log": holdings,
                "trades_log": trades_log,
                "opt_diagnostics": opt_diagnostics,
            }

        return results

    # ------------------------------------------------------------------
    # Simulation loop
    # ------------------------------------------------------------------
    def _simulate(self, scores: pd.DataFrame,
                  score_col: str,
                  signal_dates: List[int],
                  top_n: int,
                  weighting: str,
                  initial_capital: float,
                  mu_df: Optional[pd.DataFrame] = None,
                  weight_max: float = 0.02,
                  end_date: Optional[int] = None,
                  entry_rank: Optional[int] = None,
                  exit_rank: Optional[int] = None,
                  turnover_max: Optional[float] = None,
                  turnover_penalty: Optional[float] = None,
                  no_trade_band: float = 0.0,
                  max_weight_change: Optional[float] = None,
                  score_smoothing_halflife: Optional[int] = None,
                  hold_buffer_mode: str = "standard",
                  cost_aware_lambda: float = 0.0,
                  estimated_cost_bps: float = 10.0,
                  cov_shrinkage: str = "ledoit_wolf",
                  constraint_relaxation: str = "none",
                  ) -> Tuple[List[Dict], List[Dict], List[Dict], Dict]:
        """
        Simulate portfolio through rebalance dates.

        Returns (portfolio_values, holdings_log, trades_log, opt_diagnostics).
        """
        portfolio_value = initial_capital
        cash = 0.0
        prev_weights = pd.Series(dtype="float64")
        prev_exec_date = None

        portfolio_values = []
        holdings_log = []
        trades_log = []

        from data.calendar import get_calendar
        cal = get_calendar()
        end_bound = None
        if end_date is not None:
            # Last tradable mark-to-market date inside the requested window.
            # This prevents a December backtest from accidentally using prices
            # from the first trading day of the next year.
            end_bound = cal.next_trade_day(int(end_date), 0)

        # Optimizer diagnostics
        opt_n_total = 0
        opt_n_fallback = 0
        opt_n_mu_used = 0
        opt_n_low_space = 0
        opt_n_relaxation = 0  # relaxation applied (Level 1-3)
        opt_n_relaxation_success = 0  # relaxation led to success
        opt_fallback_reasons = {}  # reason -> count
        opt_active_weights = []
        opt_max_weights = []
        opt_events = []  # Batch 7: per-rebalance event log

        for i, signal_date in enumerate(signal_dates[:-1]):  # skip last (need t+1)
            # Execution date = next trading day after signal
            exec_date = cal.next_trade_day(signal_date, 1)
            exec_date_str = str(exec_date)
            signal_date_str = str(signal_date)

            if end_bound is not None and exec_date > end_bound:
                logger.debug(
                    "%d: execution date %d is beyond end_date %d; stopping",
                    signal_date, exec_date, end_bound,
                )
                break

            # Get universe at signal date
            universe = self.universe.get_universe(signal_date)

            if len(universe) < top_n:
                logger.debug(f"{signal_date}: universe too small ({len(universe)} < {top_n})")
                continue

            # Get scores for this signal date
            day_scores = scores[
                (scores["trade_date"] == signal_date) &
                (scores["ts_code"].isin(universe))
            ].dropna(subset=[score_col])

            if len(day_scores) < top_n:
                if len(day_scores) == 0:
                    logger.info(
                        "%d: no composite scores (gate rejected all factors "
                        "or min_active_factors not met) — holding positions",
                        signal_date,
                    )
                else:
                    logger.debug(
                        "%d: insufficient scored stocks (%d < %d)",
                        signal_date, len(day_scores), top_n,
                    )
                continue

            # Apply score smoothing if configured
            if score_smoothing_halflife is not None and score_smoothing_halflife > 0:
                day_scores = self._smooth_scores(
                    day_scores, score_col, signal_date, score_smoothing_halflife
                )

            # Select top N (with optional buffer logic for Phase 3)
            if entry_rank is not None and exit_rank is not None:
                top_stocks = self._select_with_buffer(
                    day_scores, score_col, top_n,
                    prev_weights, entry_rank, exit_rank
                )
            else:
                top_stocks = day_scores.nlargest(top_n, score_col)

            # Compute target weights
            if weighting == "equal":
                target_weights = pd.Series(
                    1.0 / top_n,
                    index=top_stocks["ts_code"],
                    dtype="float64"
                )
            elif weighting == "score":
                raw = top_stocks.set_index("ts_code")[score_col]
                # Softmax-like: shift to positive, normalize
                shifted = raw - raw.min() + 1e-8
                target_weights = shifted / shifted.sum()
            elif weighting == "optimized":
                opt_n_total += 1
                # Use new optimized_weighting module when available;
                # otherwise fall back to legacy _compute_optimized_weights.
                try:
                    from portfolio.optimized_weighting import compute_optimized_weights
                    target_weights, opt_diag = compute_optimized_weights(
                        top_stocks, score_col, signal_date, prev_weights,
                        exec_date, top_n, mu_df, weight_max,
                        turnover_max=turnover_max,
                        turnover_penalty=turnover_penalty,
                        cost_aware_lambda=cost_aware_lambda,
                        estimated_cost_bps=estimated_cost_bps,
                        cov_method=cov_shrinkage,
                        no_trade_band=no_trade_band,
                        max_weight_change=max_weight_change,
                        constraint_relaxation=constraint_relaxation,
                    )
                except ImportError:
                    target_weights, opt_diag = self._compute_optimized_weights(
                        top_stocks, score_col, signal_date, prev_weights,
                        exec_date, top_n, mu_df, weight_max,
                        turnover_max=turnover_max, turnover_penalty=turnover_penalty
                    )

                # Track relaxation statistics
                relax_level = opt_diag.get("relaxation_level", 0)
                if relax_level > 0:
                    opt_n_relaxation += 1
                    if not opt_diag.get("fallback"):
                        opt_n_relaxation_success += 1

                if opt_diag.get("fallback"):
                    opt_n_fallback += 1
                    reason = opt_diag.get("fallback_reason", "unknown")
                    # Classify reason for counting
                    if "infeasible" in reason:
                        reason_key = "infeasible_config"
                    elif "missing_mu" in reason:
                        reason_key = "missing_mu"
                    elif "insufficient price history" in reason:
                        reason_key = "insufficient_price_history"
                    elif "return observations" in reason:
                        reason_key = "insufficient_return_obs"
                    elif "valid stocks after cov" in reason:
                        reason_key = "insufficient_stocks_after_cov"
                    elif "did not converge" in reason or "all_relaxation" in reason:
                        reason_key = "no_convergence"
                    elif "solver failed" in reason:
                        reason_key = "solver_crash"
                    elif "non-finite" in reason:
                        reason_key = "non_finite_weights"
                    elif "zero weights" in reason:
                        reason_key = "zero_weights"
                    else:
                        reason_key = reason[:80]
                    opt_fallback_reasons[reason_key] = \
                        opt_fallback_reasons.get(reason_key, 0) + 1
                    logger.warning(
                        f"Optimizer fallback at {signal_date}: {reason}"
                    )
                if opt_diag.get("used_mu"):
                    opt_n_mu_used += 1
                if opt_diag.get("low_optimizer_space"):
                    opt_n_low_space += 1
                # Track active weights for diagnostics
                nz = target_weights[target_weights > 1e-6]
                if len(nz) > 0:
                    opt_active_weights.append(float(nz.mean()))
                    opt_max_weights.append(float(nz.max()))

                # Batch 7: Record per-rebalance optimizer event
                opt_events.append({
                    "signal_date": signal_date,
                    "exec_date": exec_date,
                    "fallback": opt_diag.get("fallback", False),
                    "fallback_reason": opt_diag.get("fallback_reason", ""),
                    "relaxation_level": opt_diag.get("relaxation_level", 0),
                    "relaxation_applied": opt_diag.get("relaxation_applied", []),
                    "constraint_relaxation_mode": opt_diag.get(
                        "constraint_relaxation_mode", ""),
                    "solver": opt_diag.get("solver", ""),
                    "n_optimized": opt_diag.get("n_optimized", 0),
                    "used_mu": opt_diag.get("used_mu", False),
                    "low_optimizer_space": opt_diag.get("low_optimizer_space", False),
                })
            else:
                raise ValueError(f"Unknown weighting: {weighting}")

            # Get execution prices (raw open at exec_date) for BOTH
            # target stocks AND previous holdings (must price sells)
            all_trade_stocks = list(
                set(target_weights.index) | set(prev_weights.index)
            )
            exec_prices = self._get_execution_prices(all_trade_stocks, exec_date_str)

            if exec_prices.empty:
                logger.debug(f"{exec_date}: no execution prices")
                continue

            # Get tradable mask at exec_date — must include BOTH target
            # stocks AND previous holdings (stocks we need to sell out of).
            # Pass raw open prices AND limit_data so limit up/down checks can work.
            all_relevant_stocks = list(
                set(target_weights.index) | set(prev_weights.index)
            )
            raw_open_for_mask = exec_prices[["ts_code", "open"]].copy()

            # Fetch limit_data for execution date
            limit_data = None
            try:
                from data.panel_loader import get_loader
                loader_ = get_loader()
                limit_data = loader_.query_limit_data(
                    exec_date_str, ts_codes=all_relevant_stocks
                )
            except Exception as e:
                logger.debug(f"Could not fetch limit_data for {exec_date_str}: {e}")

            # Fallback: try client directly if loader returned empty
            if limit_data is None or limit_data.empty:
                try:
                    limit_data = self.tradable.client.get_stk_limit(
                        ts_code=",".join(all_relevant_stocks[:500]),
                        trade_date=exec_date_str
                    )
                except Exception as e:
                    logger.debug(f"Client fallback limit_data {exec_date_str}: {e}")

            mask = self.tradable.get_mask(
                all_relevant_stocks, exec_date,
                raw_prices=raw_open_for_mask,
                limit_data=limit_data,
            )

            can_buy = mask.set_index("ts_code")["can_buy"] if not mask.empty else None
            can_sell = mask.set_index("ts_code")["can_sell"] if not mask.empty else None

            if not mask.empty and not mask["limit_check_available"].all():
                logger.warning(
                    f"Limit check unavailable for some stocks on {exec_date}. "
                    f"Can_buy/can_sell may miss limit-up/down constraints."
                )

            period_start_value = portfolio_value

            # Execute rebalance
            exec_result = self.execution.execute_rebalance(
                signal_date=signal_date,
                target_weights=target_weights,
                prev_holdings=prev_weights,
                prices=exec_prices,
                portfolio_value=portfolio_value,
                can_buy=can_buy,
                can_sell=can_sell,
            )

            executed_weights = exec_result["executed_weights"]
            costs = exec_result["costs"]
            turnover = exec_result["turnover"]

            # Deduct costs from portfolio before applying holding returns.
            portfolio_value -= costs["total_cost_cny"]
            cash = portfolio_value * exec_result["cash_drag"]

            # Compute period return (from exec_date to next exec_date)
            if i < len(signal_dates) - 1:
                next_exec_date = cal.next_trade_day(signal_dates[i + 1], 1)
            else:
                next_exec_date = exec_date + 7  # rough fallback
            if end_bound is not None and next_exec_date > end_bound:
                next_exec_date = end_bound
            if next_exec_date <= exec_date:
                logger.debug(
                    "%d: holding period has no in-window end date "
                    "(exec=%d, period_end=%d); skipping",
                    signal_date, exec_date, next_exec_date,
                )
                continue

            gross_period_return = self._compute_holding_return(
                executed_weights, exec_date, next_exec_date
            )

            # Update portfolio value
            portfolio_value = portfolio_value * (1.0 + gross_period_return)
            net_period_return = (
                portfolio_value / period_start_value - 1.0
                if period_start_value > 0 else gross_period_return
            )
            prev_weights = executed_weights

            # Log
            portfolio_values.append({
                "signal_date": signal_date,
                "exec_date": exec_date,
                "period_end": next_exec_date,
                "portfolio_value": portfolio_value,
                "period_return": net_period_return,
                "gross_period_return": gross_period_return,
                "turnover": turnover,
                "cost_cny": costs["total_cost_cny"],
                "cost_bps": costs["total_cost_bps"],
                "n_holdings": len(executed_weights[executed_weights > 1e-6]),
            })

            holdings_log.append({
                "signal_date": signal_date,
                "exec_date": exec_date,
                "weights": executed_weights.to_dict(),
            })

            trades_log.append({
                "signal_date": signal_date,
                "exec_date": exec_date,
                "turnover": turnover,
                "cost_cny": costs["total_cost_cny"],
                "cost_bps": costs["total_cost_bps"],
            })

            if (i + 1) % 50 == 0:
                logger.info(
                    f"Rebalance {i+1}/{len(signal_dates)-1}: "
                    f"value={portfolio_value:,.0f}, "
                    f"return={net_period_return:.4%}, "
                    f"turnover={turnover:.2%}"
                )

        opt_diagnostics = {
            "opt_n_total": opt_n_total,
            "opt_n_fallback": opt_n_fallback,
            "opt_n_mu_used": opt_n_mu_used,
            "opt_n_low_space": opt_n_low_space,
            "opt_n_relaxation": opt_n_relaxation,
            "opt_n_relaxation_success": opt_n_relaxation_success,
            "opt_fallback_rate": opt_n_fallback / opt_n_total if opt_n_total > 0 else 0.0,
            "opt_mu_rate": opt_n_mu_used / opt_n_total if opt_n_total > 0 else 0.0,
            "opt_relaxation_rate": opt_n_relaxation / opt_n_total if opt_n_total > 0 else 0.0,
            "opt_fallback_reasons": opt_fallback_reasons,
            "opt_avg_active_weight": float(np.mean(opt_active_weights)) if opt_active_weights else 0.0,
            "opt_max_single_weight": float(np.max(opt_max_weights)) if opt_max_weights else 0.0,
            "opt_events": opt_events,  # Batch 7: per-rebalance event log
        }

        return portfolio_values, holdings_log, trades_log, opt_diagnostics

    # ------------------------------------------------------------------
    # Performance metrics
    # ------------------------------------------------------------------
    def _compute_metrics(self,
                         portfolio_values: List[Dict],
                         benchmark_returns: pd.DataFrame,
                         holdings_log: List[Dict],
                         trades_log: List[Dict],
                         opt_diagnostics: Optional[Dict] = None) -> Dict[str, Any]:
        """Compute backtest performance metrics."""
        if not portfolio_values:
            return {"error": "No portfolio values computed"}

        pv = pd.DataFrame(portfolio_values)
        pv["trade_date"] = pv["signal_date"]
        pv = pv.set_index("trade_date").sort_index()

        # Portfolio returns
        returns = pv["period_return"].dropna()

        if len(returns) < 5:
            return {"error": "Insufficient returns", "n_periods": len(returns)}

        # Annualization factor
        periods_per_year = 52  # weekly rebalance

        # Portfolio statistics
        total_return = float((1 + returns).prod() - 1)
        ann_return = float((1 + returns).prod() ** (periods_per_year / len(returns)) - 1)
        ann_vol = float(returns.std() * np.sqrt(periods_per_year))
        sharpe = ann_return / ann_vol if ann_vol > 0 else 0.0

        # Drawdown
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.cummax()
        drawdown = cumulative / running_max - 1
        max_dd = float(drawdown.min())

        # Calmar ratio
        calmar = ann_return / abs(max_dd) if max_dd != 0 else 0.0

        # Win rate
        win_rate = float((returns > 0).mean())

        # Turnover
        avg_turnover = float(pv["turnover"].mean()) if "turnover" in pv.columns else 0.0

        # Costs
        total_cost_bps = float(pv["cost_bps"].sum()) if "cost_bps" in pv.columns else 0.0
        avg_cost_bps = float(pv["cost_bps"].mean()) if "cost_bps" in pv.columns else 0.0

        # Build period dates for benchmark alignment
        period_dates = pv[["exec_date", "period_end"]].copy() if not pv.empty else None

        # Benchmark comparison
        benchmark_stats = self._compute_benchmark_stats(
            returns, benchmark_returns, period_dates
        )

        # Holdings concentration
        avg_holdings = float(pv["n_holdings"].mean()) if "n_holdings" in pv.columns else 0.0

        # VaR (95%)
        var_95 = float(returns.quantile(0.05))

        # CVaR / ES (95%)
        cvar_95 = float(returns[returns <= var_95].mean())

        metrics = {
            "total_return": total_return,
            "annualized_return": ann_return,
            "annualized_volatility": ann_vol,
            "sharpe_ratio": sharpe,
            "max_drawdown": max_dd,
            "calmar_ratio": calmar,
            "win_rate": win_rate,
            "avg_turnover": avg_turnover,
            "total_cost_bps": total_cost_bps,
            "avg_cost_bps": avg_cost_bps,
            "avg_holdings": avg_holdings,
            "var_95": var_95,
            "cvar_95": cvar_95,
            "n_periods": len(returns),
            "period_start": str(pv["signal_date"].iloc[0]) if len(pv) > 0 else "",
            "period_end": str(pv["signal_date"].iloc[-1]) if len(pv) > 0 else "",
            "start_date": str(pv.index[0]) if len(pv) > 0 else "",
            "end_date": str(pv.index[-1]) if len(pv) > 0 else "",
        }

        # Merge benchmark stats
        metrics.update(benchmark_stats)

        # Benchmark annualized return (for comparison).
        # When benchmark data is insufficient, use None/NULL — NEVER 0.0.
        bm_status = benchmark_stats.get("benchmark_status", "UNKNOWN")
        if bm_status == "OK":
            metrics["benchmark_annualized_return"] = benchmark_stats.get(
                "benchmark_annualized_return", None
            )
        else:
            metrics["benchmark_annualized_return"] = None

        # ---- New: max single period return and stability diagnostics ----
        if len(returns) > 0:
            abs_rets = returns.abs()
            max_idx = abs_rets.idxmax()
            metrics["max_single_period_return"] = float(returns.loc[max_idx])
            metrics["max_single_period_return_date"] = str(max_idx)
            metrics["period_return_std"] = float(returns.std())
        else:
            metrics["max_single_period_return"] = None
            metrics["max_single_period_return_date"] = None
            metrics["period_return_std"] = None

        # ---- Max AND min single period return ----
        if len(returns) > 0:
            min_idx = returns.idxmin()
            metrics["min_single_period_return"] = float(returns.loc[min_idx])
            metrics["min_single_period_return_date"] = str(min_idx)
        else:
            metrics["min_single_period_return"] = None
            metrics["min_single_period_return_date"] = None

        # Metric stability: YTD annualized from < 26 weekly samples is UNSTABLE
        metrics["metric_stability_status"] = (
            "UNSTABLE" if len(returns) < 26 else "STABLE"
        )
        metrics["n_weekly_samples"] = len(returns)

        # Data quality status — aggregate from benchmark and price quality
        metrics["data_quality_status"] = "OK" if bm_status == "OK" else bm_status
        # price_quality_status is set by Phase 0 validation, propagate if present
        # (not yet set by backtester — will be wired from run_research.py)

        # ---- Merge optimizer diagnostics ----
        if opt_diagnostics and opt_diagnostics.get("opt_n_total", 0) > 0:
            metrics.update({
                "optimizer_fallback_rate": opt_diagnostics.get("opt_fallback_rate", 0.0),
                "optimizer_relaxation_rate": opt_diagnostics.get("opt_relaxation_rate", 0.0),
                "used_mu_rate": opt_diagnostics.get("opt_mu_rate", 0.0),
                "avg_active_weight": opt_diagnostics.get("opt_avg_active_weight", 0.0),
                "max_single_weight": opt_diagnostics.get("opt_max_single_weight", 0.0),
                "opt_n_total": opt_diagnostics.get("opt_n_total", 0),
                "opt_n_fallback": opt_diagnostics.get("opt_n_fallback", 0),
                "opt_n_low_space": opt_diagnostics.get("opt_n_low_space", 0),
                "opt_n_relaxation": opt_diagnostics.get("opt_n_relaxation", 0),
                "opt_n_relaxation_success": opt_diagnostics.get("opt_n_relaxation_success", 0),
                "opt_fallback_reasons": opt_diagnostics.get("opt_fallback_reasons", {}),
            })

        # Go/No-Go summary — gated by benchmark_status AND data quality
        # Use the data quality gate for structured output
        data_gate = self._compute_data_quality_gate(metrics)
        metrics["go_nogo"] = {
            "overall": data_gate["overall"],
            "data_quality": data_gate["data_quality"],
            "benchmark_status": data_gate["benchmark_status"],
            "price_quality_status": data_gate["price_quality_status"],
            "metric_stability_status": data_gate["metric_stability_status"],
            "failure_reasons": data_gate["failure_reasons"],
            # Legacy fields for backward compatibility
            "positive_excess_return": (
                metrics.get("annualized_excess_return", 0) > 0
                if bm_status == "OK" else False
            ),
            "positive_ir": (
                metrics.get("information_ratio", 0) > 0
                if bm_status == "OK" else False
            ),
            "acceptable_max_dd": abs(max_dd) < 0.25,
            "cost_2x_survivable": bm_status == "OK",
        }
        metrics["_data_quality_gate"] = data_gate

        return metrics

    # ------------------------------------------------------------------
    # Benchmark
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Data quality gate (Stage 6)
    # ------------------------------------------------------------------
    @staticmethod
    def _compute_data_quality_gate(metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compute data-quality gate verdict independently of performance checks.

        Returns structured output with:
            overall: GO | NO-GO | NO_GO_DATA_INVALID
            data_quality: OK | FAIL
            benchmark_status, price_quality_status, metric_stability_status
            failure_reasons: list[str]
        """
        failure_reasons = []
        checks = {}

        # Gate 1: benchmark_status must be OK
        bm_status = metrics.get("benchmark_status", "UNKNOWN")
        checks["benchmark_status"] = bm_status
        if bm_status != "OK":
            failure_reasons.append(
                f"benchmark_status={bm_status} "
                f"(reason: {metrics.get('benchmark_failure_reason', 'N/A')})"
            )

        # Gate 2: price_quality_status (if available)
        pq_status = metrics.get("price_quality_status", None)
        if pq_status is not None:
            checks["price_quality_status"] = pq_status
            if pq_status != "OK":
                failure_reasons.append(f"price_quality_status={pq_status}")

        # Gate 3: data_quality_status
        dq_status = metrics.get("data_quality_status", "UNKNOWN")
        checks["data_quality_status"] = dq_status
        if dq_status != "OK":
            failure_reasons.append(f"data_quality_status={dq_status}")

        # Gate 4: minimum sample periods
        n_periods = metrics.get("n_periods", 0)
        checks["n_periods"] = n_periods
        if n_periods < 5:
            failure_reasons.append(
                f"n_periods={n_periods} < 5 (INSUFFICIENT)"
            )
        elif n_periods < 26:
            checks["n_periods_warning"] = "UNSTABLE"
            # Not a hard fail but logged

        # Gate 5: no extreme single-period returns (suggests data corruption)
        max_single = metrics.get("max_single_period_return")
        if max_single is not None and isinstance(max_single, (int, float)):
            checks["max_single_period_return"] = float(max_single)
            # Default threshold: 30% weekly (configurable)
            threshold = 0.30
            if abs(max_single) > threshold:
                failure_reasons.append(
                    f"max_single_period_return={max_single:.2%} exceeds {threshold:.0%} "
                    f"(date={metrics.get('max_single_period_return_date', 'N/A')})"
                )

        # Gate 6: key metrics must be finite
        for key in ("annualized_return", "sharpe_ratio", "information_ratio"):
            val = metrics.get(key)
            if val is not None and isinstance(val, float) and not np.isfinite(val):
                failure_reasons.append(f"{key} is not finite: {val}")

        # Metric stability
        stability = metrics.get("metric_stability_status", "UNKNOWN")
        checks["metric_stability_status"] = stability

        # Compute overall
        if failure_reasons:
            overall = "NO_GO_DATA_INVALID"
            data_quality = "FAIL"
        elif stability == "UNSTABLE":
            overall = "NO-GO"
            data_quality = "OK"
        else:
            overall = "GO"
            data_quality = "OK"

        return {
            "overall": overall,
            "data_quality": data_quality,
            "benchmark_status": bm_status,
            "price_quality_status": pq_status or "NOT_CHECKED",
            "metric_stability_status": stability,
            "failure_reasons": failure_reasons,
            "checks": checks,
        }

    # ------------------------------------------------------------------
    # Benchmark
    # ------------------------------------------------------------------
    def _load_benchmark_returns(self, benchmark_code: str,
                                start_date: str, end_date: str) -> pd.DataFrame:
        """Load benchmark (CSI 300) daily returns.

        Checks index_daily .attrs for cache quality diagnostics and logs
        warnings when partial/incomplete data is detected.
        """
        try:
            from data.tushare_client import get_client
            client = get_client()
            idx = client.get_index_daily(
                index_code=benchmark_code,
                start_date=start_date,
                end_date=end_date
            )

            # Check for strict-mode diagnostic attrs
            idx_attrs = getattr(idx, "attrs", {})
            idx_status = idx_attrs.get("status", None)
            if idx_status in ("PARTIAL_CACHE", "FETCH_FAILED"):
                logger.error(
                    f"Benchmark index_daily {idx_status}: "
                    f"reason={idx_attrs.get('reason')}, "
                    f"coverage={idx_attrs.get('coverage_ratio', 0):.1%}, "
                    f"requested={idx_attrs.get('requested_start')}-"
                    f"{idx_attrs.get('requested_end')}"
                )
                # Store diagnostics on returned DataFrame
                if not idx.empty:
                    idx.attrs = idx_attrs

            if idx.empty:
                empty = pd.DataFrame()
                empty.attrs = {"benchmark_load_status": "MISSING"}
                return empty

            idx = idx.sort_values("trade_date")
            idx["benchmark_ret"] = idx["close"].pct_change().astype("float32")
            result = idx[["trade_date", "close", "benchmark_ret"]].dropna()
            if idx_attrs:
                result.attrs = idx_attrs
            return result
        except Exception as e:
            logger.warning(f"Failed to load benchmark: {e}")
            return pd.DataFrame()

    def _compute_benchmark_stats(self,
                                  strategy_returns: pd.Series,
                                  benchmark_returns: pd.DataFrame,
                                  period_dates: Optional[pd.DataFrame] = None
                                  ) -> Dict[str, Any]:
        """
        Compute benchmark-relative statistics.

        IMPORTANT: Strategy returns are period returns (e.g., weekly),
        so benchmark returns must be computed over the SAME holding period,
        not aligned to the same calendar day.

        ALWAYS returns a diagnostic dict — never returns empty {}.
        Callers must check `benchmark_status` to determine data validity.
        """
        # ---- Data availability checks ----
        if benchmark_returns.empty:
            return {
                "benchmark_status": "MISSING",
                "benchmark_daily_rows": 0,
                "benchmark_valid_periods": 0,
                "benchmark_start": None,
                "benchmark_end": None,
                "benchmark_failure_reason": (
                    "benchmark_returns is empty — index_daily cache may be "
                    "missing or the requested benchmark_code may not exist"
                ),
            }

        n_bench_daily = len(benchmark_returns)
        bench_start = str(benchmark_returns["trade_date"].min())
        bench_end = str(benchmark_returns["trade_date"].max())

        bench = benchmark_returns.set_index("trade_date")["benchmark_ret"]

        # If period dates are provided, compute benchmark period returns
        # matching the strategy holding periods exactly
        if period_dates is not None and not period_dates.empty:
            bench_period_rets = []
            for _, row in period_dates.iterrows():
                exec_date = row["exec_date"]
                period_end = row["period_end"]

                # Benchmark period: (exec_date, period_end] — strictly after exec_date.
                # Strategy return = adj_close[period_end] / adj_close[exec_date] - 1,
                # so benchmark must use close-to-close over the same interval.
                # Daily return at exec_date is prev_close→exec_date close — excluded.
                period_bench = bench.loc[
                    (bench.index > exec_date) & (bench.index <= period_end)
                ]
                if len(period_bench) > 0:
                    bench_ret = (1 + period_bench).prod() - 1
                    bench_period_rets.append(bench_ret)
                else:
                    bench_period_rets.append(np.nan)

            bench = pd.Series(bench_period_rets, index=strategy_returns.index)
        else:
            # Fallback: align to same dates (only correct for daily strategies)
            bench = bench.reindex(strategy_returns.index)
            logger.warning("Benchmark aligned by date, not period — "
                           "may distort IR for non-daily strategies")

        # Excess returns
        excess = strategy_returns - bench
        excess = excess.dropna()
        n_valid_periods = len(excess)

        if n_valid_periods < 5:
            return {
                "benchmark_status": "INSUFFICIENT",
                "benchmark_daily_rows": n_bench_daily,
                "benchmark_valid_periods": n_valid_periods,
                "benchmark_start": bench_start,
                "benchmark_end": bench_end,
                "benchmark_failure_reason": (
                    f"Only {n_valid_periods} valid excess return periods "
                    f"(need >=5) — strategy returns and benchmark may not overlap"
                ),
            }

        periods_per_year = 52

        # Benchmark annualized return (for unified comparison)
        bench_ann_return = float(
            (1 + bench).prod() ** (periods_per_year / len(bench)) - 1
        ) if len(bench) > 0 else 0.0

        ann_excess = float(excess.mean() * periods_per_year)
        ann_tracking_error = float(excess.std() * np.sqrt(periods_per_year))
        information_ratio = ann_excess / ann_tracking_error if ann_tracking_error > 0 else 0.0

        # Cumulative excess
        cum_excess = (1 + excess).cumprod()
        max_excess_dd = float(
            (cum_excess / cum_excess.cummax() - 1).min()
        )

        # Excess win rate
        excess_win_rate = float((excess > 0).mean())

        # Hit rate (strategy up when benchmark up)
        aligned = pd.DataFrame({
            "strategy": strategy_returns,
            "benchmark": bench
        }).dropna()
        hit_rate = float(
            ((aligned["strategy"] > 0) & (aligned["benchmark"] > 0) |
             (aligned["strategy"] < 0) & (aligned["benchmark"] < 0)).mean()
        )

        # Store benchmark period returns for diagnostic artifacts
        bench_period_df = pd.DataFrame({
            "strategy_return": strategy_returns.values,
            "benchmark_return": bench.values if hasattr(bench, "values") else bench,
        }, index=strategy_returns.index)
        # Add exec_date / period_end if available
        if period_dates is not None and not period_dates.empty:
            bench_period_df["exec_date"] = period_dates["exec_date"].values
            bench_period_df["period_end"] = period_dates["period_end"].values

        return {
            "benchmark_status": "OK",
            "benchmark_daily_rows": n_bench_daily,
            "benchmark_valid_periods": n_valid_periods,
            "benchmark_start": bench_start,
            "benchmark_end": bench_end,
            "benchmark_failure_reason": None,
            "benchmark_annualized_return": bench_ann_return,
            "annualized_excess_return": ann_excess,
            "tracking_error": ann_tracking_error,
            "information_ratio": information_ratio,
            "max_excess_drawdown": max_excess_dd,
            "excess_win_rate": excess_win_rate,
            "hit_rate": hit_rate,
            "_benchmark_period_returns": bench_period_df,
        }

    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Score smoothing (Phase C: turnover control)
    # ------------------------------------------------------------------
    @staticmethod
    def _smooth_scores(day_scores, score_col, signal_date,
                       halflife: int):
        """
        Apply exponential smoothing to composite scores using cross-sectional
        rank history. This reduces noise-driven turnover without modifying the
        underlying factor construction.

        halflife is in periods (weeks for weekly rebalance).
        """
        # Score smoothing is applied at the composite level:
        # smoothed_score = alpha * current_score + (1-alpha) * prior_smoothed_score
        # where alpha = 1 - exp(-ln(2) / halflife)
        # Since we don't have per-stock score history in this static method,
        # we approximate by dampening cross-sectional score dispersion.
        # Full implementation requires passing a score history cache.
        if halflife <= 0 or day_scores.empty:
            return day_scores

        # Gentle winsorization to reduce outlier-driven turnover
        alpha = 1.0 - np.exp(-np.log(2) / halflife)
        scores = day_scores[score_col].values
        mean_score = np.nanmean(scores)
        std_score = np.nanstd(scores) if np.nanstd(scores) > 0 else 1.0

        # Clip extreme scores at 3 std
        upper = mean_score + 3 * std_score
        lower = mean_score - 3 * std_score

        result = day_scores.copy()
        result[score_col] = np.clip(scores, lower, upper)
        # Apply slight mean reversion toward cross-sectional mean
        result[score_col] = result[score_col] * (1 - alpha * 0.5) + mean_score * alpha * 0.5

        return result

    # ------------------------------------------------------------------
    # Buffer selection (Phase 3)
    # ------------------------------------------------------------------
    @staticmethod
    def _select_with_buffer(day_scores, score_col, top_n,
                            prev_weights, entry_rank, exit_rank):
        """
        Buffer selection to reduce turnover.

        Logic:
        1. Current positions in Top `exit_rank` → retain (can adjust weight)
        2. Current positions NOT in Top `exit_rank` → forced exit
        3. New candidates must be in Top `entry_rank`
        4. Final pool: up to `top_n` stocks, prioritizing retained + top new

        Returns: filtered day_scores DataFrame.
        """
        if prev_weights is None or len(prev_weights) == 0:
            # No previous positions — fall back to simple top_n selection
            return day_scores.nlargest(top_n, score_col)

        prev_codes = set(prev_weights[prev_weights > 1e-6].index)

        # Rank all stocks by score
        ranked = day_scores.sort_values(score_col, ascending=False)
        ranked["rank"] = range(1, len(ranked) + 1)

        # Retain: current holdings that are still in Top exit_rank
        retain = ranked[
            (ranked["ts_code"].isin(prev_codes)) &
            (ranked["rank"] <= exit_rank)
        ]

        # New candidates: stocks in Top entry_rank, NOT already held
        new_candidates = ranked[
            (~ranked["ts_code"].isin(prev_codes)) &
            (ranked["rank"] <= entry_rank)
        ]

        # Combine: retain first (prioritize best-ranked), then fill slots
        # IMPORTANT: do NOT use nsmallest(top_n, "rank") on the combined set
        # because that would kick out rank 51-80 retained stocks in favor of
        # new candidates ranked 1-50, defeating the buffer.
        retain = retain.sort_values("rank").head(top_n)
        slots = top_n - len(retain)
        new_fill = new_candidates.sort_values("rank").head(slots)
        combined = pd.concat([retain, new_fill], ignore_index=True)
        # drop_duplicates guards against a stock appearing in both sets
        combined = combined.drop_duplicates("ts_code", keep="first")

        return combined

    # ------------------------------------------------------------------
    # Optimized weighting
    # ------------------------------------------------------------------
    @staticmethod
    def _compute_log_return_matrix(price_window: pd.DataFrame) -> pd.DataFrame:
        """Compute log returns while preserving partially observed dates."""
        if price_window.empty:
            return pd.DataFrame()

        ret_matrix = np.log(price_window / price_window.shift(1))
        ret_matrix = ret_matrix.replace([np.inf, -np.inf], np.nan)
        return ret_matrix.dropna(how="all")

    @staticmethod
    def _ensure_psd(Sigma: np.ndarray, epsilon: float = 1e-6) -> np.ndarray:
        """Return a finite positive semi-definite covariance matrix."""
        Sigma = np.asarray(Sigma, dtype="float64")
        Sigma = np.nan_to_num(Sigma, nan=0.0, posinf=0.0, neginf=0.0)
        Sigma = (Sigma + Sigma.T) / 2.0

        eigenvalues = np.linalg.eigvalsh(Sigma)
        min_eig = float(eigenvalues.min()) if len(eigenvalues) else 0.0
        if min_eig < epsilon:
            Sigma = Sigma + np.eye(Sigma.shape[0]) * (epsilon - min_eig)
        return Sigma

    def _compute_optimized_weights(self, top_stocks, score_col, signal_date,
                                   prev_weights, exec_date, top_n,
                                   mu_df=None, weight_max=0.02,
                                   turnover_max=None, turnover_penalty=None):
        """
        Compute mean-variance optimized weights.

        Uses mu_df["mu"] as expected returns (NOT composite_score).
        Falls back to equal-weight on any failure.
        Returns (weights_series, diagnostics_dict).
        """
        diag = {"fallback": False, "fallback_reason": "", "used_mu": False,
                "low_optimizer_space": False}
        equal_weights = pd.Series(1.0 / top_n, index=top_stocks["ts_code"],
                                  dtype="float64")

        # Feasibility check: top_n * weight_max must be >= 1.0 for long-only
        opt_space = top_n * weight_max
        if opt_space < 1.0:
            diag["fallback"] = True
            diag["fallback_reason"] = (
                f"infeasible: top_n={top_n} * weight_max={weight_max} "
                f"= {opt_space:.2f} < 1.0 — cannot fully invest"
            )
            diag["infeasible_config"] = True
            return equal_weights, diag
        # Track when optimizer has very little space to deviate from equal-weight
        if opt_space <= 1.05:
            diag["low_optimizer_space"] = True

        try:
            import cvxpy as cp
        except ImportError:
            diag["fallback"] = True
            diag["fallback_reason"] = "cvxpy not installed"
            return equal_weights, diag

        stock_codes = list(top_stocks["ts_code"])

        # Get expected returns: use mu_df["mu"] if available, NOT composite_score
        if mu_df is not None and not mu_df.empty:
            mu_day = mu_df[
                (mu_df["trade_date"] == signal_date) &
                (mu_df["ts_code"].isin(stock_codes))
            ]
            if not mu_day.empty and "mu" in mu_day.columns:
                mu_series = (
                    mu_day.set_index("ts_code")["mu"]
                    .astype("float64")
                    .replace([np.inf, -np.inf], np.nan)
                    .fillna(0.0)
                )
                diag["used_mu"] = True
            else:
                diag["fallback"] = True
                diag["fallback_reason"] = f"missing_mu for {signal_date}"
                return equal_weights, diag
        else:
            diag["fallback"] = True
            diag["fallback_reason"] = "missing_mu — no mu_df provided"
            return equal_weights, diag

        # Build mu vector
        mu = mu_series.reindex(stock_codes, fill_value=0.0).values.astype("float64")

        # Estimate covariance from historical returns
        try:
            # Get historical adj_close for these stocks
            # Use trading-day calendar for proper lookback (NOT int subtraction)
            from data.panel_loader import get_loader
            from data.calendar import get_calendar
            loader_ = get_loader()
            cal = get_calendar()
            lookback_start = str(cal.prev_trade_day(exec_date, 252))
            price_window = loader_.pivot_for_window(
                start_date=lookback_start,
                end_date=str(exec_date),
                ts_codes=stock_codes,
                field="adj_close"
            )

            if price_window.empty or price_window.shape[1] < 5:
                diag["fallback"] = True
                diag["fallback_reason"] = "insufficient price history for covariance"
                return equal_weights, diag

            # Compute log returns.  Keep partially observed dates; the
            # covariance estimator filters stocks by per-name min_obs.
            ret_matrix = self._compute_log_return_matrix(price_window)
            if ret_matrix.shape[0] < 60:
                diag["fallback"] = True
                diag["fallback_reason"] = f"only {ret_matrix.shape[0]} return observations"
                return equal_weights, diag

            # Estimate covariance
            from portfolio.cov_estimator import CovarianceEstimator
            cov_est = CovarianceEstimator(method="ledoit_wolf", window=252, min_obs=60)
            Sigma, codes = cov_est.estimate(ret_matrix)

            if len(codes) < 5:
                diag["fallback"] = True
                diag["fallback_reason"] = f"only {len(codes)} valid stocks after cov estimation"
                return equal_weights, diag
            Sigma = self._ensure_psd(Sigma)

            # Build constraint set
            n = len(codes)
            code_to_idx = {c: i for i, c in enumerate(codes)}

            # Align mu to codes
            mu_aligned = np.array([
                mu_series.get(c, 0.0) for c in codes
            ], dtype="float64")

            # Previous weights aligned to codes
            prev_aligned = np.array([
                prev_weights.get(c, 0.0) if prev_weights is not None else 0.0
                for c in codes
            ], dtype="float64")

            # Decision variable
            w = cp.Variable(n)

            # Objective: max w'μ - (λ/2) * w'Σw
            risk_aversion = 1.0
            objective = cp.Maximize(mu_aligned @ w - (risk_aversion / 2) * cp.quad_form(w, Sigma))

            # Constraints
            constraints = [
                cp.sum(w) == 1.0,
                w >= 0,
                w <= weight_max,
            ]

            # Turnover constraint (configurable, default 60%)
            _to_max = turnover_max if turnover_max is not None else 0.60
            if prev_aligned.sum() > 0 and _to_max < 1.0:
                constraints.append(
                    cp.sum(cp.abs(w - prev_aligned)) / 2.0 <= _to_max
                )

            # Turnover penalty in objective (Phase 3)
            _to_penalty = turnover_penalty if turnover_penalty is not None else 0.0
            if _to_penalty > 0 and prev_aligned.sum() > 0:
                objective = cp.Maximize(
                    mu_aligned @ w
                    - (risk_aversion / 2) * cp.quad_form(w, Sigma)
                    - _to_penalty * cp.sum(cp.abs(w - prev_aligned))
                )

            # Solve.  Some solvers can return inaccurate/non-finite values on
            # ill-conditioned covariance matrices, so validate and retry.
            installed = set(cp.installed_solvers())
            solver_attempts = [
                ("ECOS", {"max_iters": 10000}),
                ("CLARABEL", {}),
                ("OSQP", {
                    "max_iter": 20000,
                    "eps_abs": 1e-6,
                    "eps_rel": 1e-6,
                }),
            ]
            last_reason = "optimization did not converge"
            optimal = None
            acceptable_status = {"optimal", "optimal_inaccurate"}

            for solver_name, solver_kwargs in solver_attempts:
                if solver_name not in installed:
                    continue

                problem = cp.Problem(objective, constraints)
                try:
                    problem.solve(
                        solver=solver_name,
                        verbose=False,
                        **solver_kwargs,
                    )
                except Exception as e:
                    last_reason = f"{solver_name} solver failed: {str(e)[:60]}"
                    continue

                if problem.status not in acceptable_status or w.value is None:
                    last_reason = f"{solver_name} status {problem.status}"
                    continue

                candidate = np.asarray(w.value, dtype="float64").reshape(-1)
                if candidate.shape[0] != n or not np.all(np.isfinite(candidate)):
                    last_reason = f"{solver_name} returned non-finite weights"
                    continue

                candidate[candidate < 1e-6] = 0.0
                weight_sum = float(candidate.sum())
                if not np.isfinite(weight_sum) or weight_sum <= 1e-12:
                    last_reason = f"{solver_name} returned zero weights"
                    continue

                optimal = candidate / weight_sum
                diag["solver"] = solver_name
                break

            if optimal is None:
                diag["fallback"] = True
                diag["fallback_reason"] = last_reason
                return equal_weights, diag

            result = pd.Series(optimal, index=codes, dtype="float64")
            diag["n_optimized"] = int((optimal > 1e-6).sum())
            return result, diag

        except Exception as e:
            diag["fallback"] = True
            diag["fallback_reason"] = str(e)[:100]
            return equal_weights, diag

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_execution_prices(self, ts_codes: List[str],
                              date_str: str) -> pd.DataFrame:
        """Get raw open prices for execution date."""
        try:
            prices = self.loader.query_prices(
                start_date=date_str, end_date=date_str,
                ts_codes=ts_codes,
                fields=["ts_code", "trade_date", "open"],
                price_type="raw"
            )
            return prices
        except Exception as e:
            logger.debug(f"Failed to get execution prices for {date_str}: {e}")
            return pd.DataFrame()

    def _compute_holding_return(self,
                                 weights: pd.Series,
                                 exec_date: int,
                                 next_exec_date: int) -> float:
        """
        Compute portfolio return from exec_date to next_exec_date.

        Uses adj_close for return calculation.
        """
        codes = list(weights[weights > 1e-6].index)
        if not codes:
            return 0.0

        try:
            # Get adj_close at start and end
            start_prices = self.loader.query_prices(
                start_date=str(exec_date), end_date=str(exec_date),
                ts_codes=codes,
                fields=["ts_code", "adj_close"],
                price_type="adj"
            )
            end_prices = self.loader.query_prices(
                start_date=str(next_exec_date), end_date=str(next_exec_date),
                ts_codes=codes,
                fields=["ts_code", "adj_close"],
                price_type="adj"
            )

            if start_prices.empty or end_prices.empty:
                return 0.0

            p0 = start_prices.set_index("ts_code")["adj_close"]
            p1 = end_prices.set_index("ts_code")["adj_close"]

            # Align
            common = set(p0.index) & set(p1.index) & set(weights.index)
            if not common:
                return 0.0

            w = weights.reindex(list(common), fill_value=0.0)
            w = w / w.sum() if w.sum() > 0 else w

            stock_ret = p1.reindex(list(common)) / p0.reindex(list(common)) - 1.0
            portfolio_ret = (w * stock_ret).sum()

            return float(portfolio_ret)
        except Exception as e:
            logger.debug(f"Return computation error ({exec_date}->{next_exec_date}): {e}")
            return 0.0

    # ------------------------------------------------------------------
    # Report generation
    # ------------------------------------------------------------------
    def generate_report(self, results: Dict[str, Any], run_id: str = None) -> str:
        """Generate markdown backtest report."""
        lines = []
        lines.append("# Portfolio Backtest Report")
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        if run_id:
            lines.append(f"Run ID: {run_id}")
        lines.append("")

        config = results.get("config", {})
        lines.append("## Configuration")
        lines.append(f"- Period: {config.get('start_date', '')} to {config.get('end_date', '')}")
        lines.append(f"- Top N: {config.get('top_n', '')}")
        lines.append(f"- Weighting: {config.get('weighting', '')}")
        lines.append(f"- Rebalance: {config.get('rebalance_freq', '')}")
        lines.append(f"- Initial Capital: {config.get('initial_capital', 0):,.0f}")
        lines.append(f"- Weight Max: {config.get('weight_max', 0):.1%}")
        lines.append(f"- Cost Multiplier: {config.get('cost_multiplier', 1.0)}x")
        if config.get('slippage_bps') is not None:
            lines.append(f"- Slippage: {config.get('slippage_bps')}bp")
        if config.get('entry_rank'):
            lines.append(f"- Entry Rank: {config.get('entry_rank')}")
        if config.get('exit_rank'):
            lines.append(f"- Exit Rank: {config.get('exit_rank')}")
        lines.append("")

        lines.append("## Performance Metrics")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| N Periods | {results.get('n_periods', 0)} |")
        lines.append(f"| Period | {results.get('period_start', '')} → {results.get('period_end', '')} |")
        lines.append(f"| Total Return | {results.get('total_return', 0):.2%} |")
        lines.append(f"| Annualized Return | {results.get('annualized_return', 0):.2%} |")
        lines.append(f"| Annualized Volatility | {results.get('annualized_volatility', 0):.2%} |")
        lines.append(f"| Sharpe Ratio | {results.get('sharpe_ratio', 0):.3f} |")
        lines.append(f"| Max Drawdown | {results.get('max_drawdown', 0):.2%} |")
        lines.append(f"| Calmar Ratio | {results.get('calmar_ratio', 0):.3f} |")
        lines.append(f"| Win Rate | {results.get('win_rate', 0):.2%} |")
        lines.append(f"| Avg Turnover | {results.get('avg_turnover', 0):.2%} |")
        lines.append(f"| Total Cost (bps) | {results.get('total_cost_bps', 0):.1f} |")
        lines.append(f"| Avg Holdings | {results.get('avg_holdings', 0):.0f} |")
        lines.append(f"| VaR 95% | {results.get('var_95', 0):.2%} |")
        lines.append(f"| CVaR 95% | {results.get('cvar_95', 0):.2%} |")
        lines.append("")

        # Benchmark relative
        bm_status = results.get("benchmark_status", "UNKNOWN")
        lines.append("## vs CSI 300 Benchmark")
        if bm_status != "OK":
            bm_reason = results.get("benchmark_failure_reason", "Unknown reason")
            lines.append(f"**STATUS: {bm_status}** — {bm_reason}")
            lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        # Helper: show NA for None/NaN benchmark values
        def _bm_fmt(val, fmt_str=".2%"):
            if val is None:
                return "NA - benchmark data insufficient"
            if isinstance(val, float) and np.isnan(val):
                return "NA - benchmark data insufficient"
            try:
                return format(float(val), fmt_str)
            except (TypeError, ValueError):
                return str(val)
        lines.append(f"| Benchmark Ann. Return | {_bm_fmt(results.get('benchmark_annualized_return'))} |")
        lines.append(f"| Annualized Excess Return | {_bm_fmt(results.get('annualized_excess_return'))} |")
        lines.append(f"| Tracking Error | {_bm_fmt(results.get('tracking_error'))} |")
        lines.append(f"| Information Ratio | {_bm_fmt(results.get('information_ratio'), '.3f')} |")
        lines.append(f"| Max Excess Drawdown | {_bm_fmt(results.get('max_excess_drawdown'))} |")
        lines.append(f"| Excess Win Rate | {_bm_fmt(results.get('excess_win_rate'))} |")
        lines.append(f"| Hit Rate | {_bm_fmt(results.get('hit_rate'))} |")
        lines.append("")

        # Optimizer diagnostics (if available AND has actual optimization runs)
        if (results.get("optimizer_fallback_rate") is not None
                and results.get("opt_n_total", 0) > 0):
            lines.append("## Optimizer Diagnostics")
            lines.append("| Metric | Value |")
            lines.append("|--------|-------|")
            lines.append(f"| Total Optimizations | {results.get('opt_n_total', 0)} |")
            lines.append(f"| Fallback Count | {results.get('opt_n_fallback', 0)} |")
            lines.append(f"| Fallback Rate | {results.get('optimizer_fallback_rate', 0):.2%} |")
            lines.append(f"| Mu Usage Rate | {results.get('used_mu_rate', 0):.2%} |")
            lines.append(f"| Low Optimizer Space | {results.get('opt_n_low_space', 0)} |")
            lines.append(f"| Avg Active Weight | {results.get('avg_active_weight', 0):.4f} |")
            lines.append(f"| Max Single Weight | {results.get('max_single_weight', 0):.4f} |")
            # Fallback reason breakdown
            reasons = results.get("opt_fallback_reasons", {})
            if reasons:
                top5 = sorted(reasons.items(), key=lambda x: -x[1])[:5]
                lines.append("")
                lines.append("### Fallback Reason Top 5")
                lines.append("| Reason | Count |")
                lines.append("|--------|-------|")
                for reason, count in top5:
                    lines.append(f"| {reason} | {count} |")
            lines.append("")

        # Go/No-Go
        gn = results.get("go_nogo", {})
        overall = gn.get("overall", "UNKNOWN")
        lines.append("## Go/No-Go Assessment")
        # Show overall verdict prominently
        if overall == "NO_GO_DATA_INVALID":
            lines.append(f"**OVERALL: NO_GO_DATA_INVALID** — Data quality gates failed")
        elif overall == "NO-GO":
            lines.append(f"**OVERALL: NO-GO** — Performance gates failed")
        elif overall == "GO":
            lines.append(f"**OVERALL: GO** — All gates passed")
        else:
            lines.append(f"**OVERALL: {overall}**")

        # Show data quality status
        dq = gn.get("data_quality", "UNKNOWN")
        bm = gn.get("benchmark_status", "UNKNOWN")
        pq = gn.get("price_quality_status", "UNKNOWN")
        ms = gn.get("metric_stability_status", "UNKNOWN")
        lines.append(f"- Data Quality: {dq} | Benchmark: {bm} | Price Quality: {pq} | Stability: {ms}")

        # Show failures
        failures = gn.get("failure_reasons", [])
        if failures:
            lines.append("- **Failures:**")
            for f in failures:
                lines.append(f"  - {f}")

        # YTD UNSTABLE flag
        if ms == "UNSTABLE":
            lines.append("- **WARNING: YTD annualized metrics are UNSTABLE** (< 26 week samples)")

        # DATA INVALID flag for extreme single-period returns
        max_single = results.get("max_single_period_return")
        if max_single is not None and abs(max_single) > 0.30:
            lines.append(
                f"- **DATA INVALID: max single-period return = {max_single:.2%}** "
                f"(date: {results.get('max_single_period_return_date')})"
            )

        lines.append("")
        lines.append("| Criterion | Result |")
        lines.append("|-----------|--------|")
        lines.append(f"| Positive Excess Return | {'PASS' if gn.get('positive_excess_return') else 'FAIL'} |")
        lines.append(f"| Positive IR | {'PASS' if gn.get('positive_ir') else 'FAIL'} |")
        lines.append(f"| Acceptable Max DD | {'PASS' if gn.get('acceptable_max_dd') else 'FAIL'} |")
        lines.append("")

        return "\n".join(lines)

"""
Deterministic Portfolio Simulator (Phase 5H).

Models institutional portfolio accounting, concurrent position tracking,
capital allocation, and execution friction for 5-session forward return targets.
"""

from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd

from src.portfolio.schema import (
    PositionStatus,
    OrderRejectionReason,
    PortfolioConfig,
    PositionRecord,
    DailyPortfolioSnapshot,
    PortfolioSimulationResult,
)


class DeterministicPortfolioSimulator:
    """
    Executes chronological portfolio simulations with realistic capital constraints,
    concurrent holding limits, and exact transaction friction accounting.
    """

    def __init__(self, config: Optional[PortfolioConfig] = None):
        self.config = config or PortfolioConfig()

    def simulate(
        self,
        decisions_df: pd.DataFrame,
        market_df: pd.DataFrame,
        strategy_name: str = "Decision_Policy_Simulation",
    ) -> PortfolioSimulationResult:
        """
        Runs an end-to-end chronological portfolio simulation.

        :param decisions_df: DataFrame with ['trading_date', 'ticker', 'company_id', 'signal', 'expected_net_return']
        :param market_df: DataFrame with ['trading_date', 'ticker', 'open', 'close', 'adjusted_close']
        :param strategy_name: Descriptive label for reporting.
        :return: PortfolioSimulationResult containing full history and metrics.
        """
        if market_df.empty:
            raise ValueError("Cannot simulate portfolio on empty market dataset.")

        # 1. Prepare and index pricing data
        price_lookup, calendar_sessions = self._prepare_market_pricing(market_df)

        # 2. Prepare decisions map by date
        decisions_by_date = self._prepare_decisions_map(decisions_df)

        # 3. Initialize state variables
        cash = float(self.config.initial_cash)
        equity = float(self.config.initial_cash)
        peak_equity = float(self.config.initial_cash)
        total_realized_pnl = 0.0
        total_costs_incurred = 0.0

        open_positions: List[PositionRecord] = []
        pending_entries: List[PositionRecord] = []
        closed_positions: List[PositionRecord] = []
        rejected_orders: List[PositionRecord] = []
        daily_history: List[DailyPortfolioSnapshot] = []

        cost_cfg = self.config.cost_config
        one_way_entry_rate = (cost_cfg.entry_fee_bps + cost_cfg.half_spread_bps + cost_cfg.slippage_bps) / 10000.0
        one_way_exit_rate = (cost_cfg.exit_fee_bps + cost_cfg.half_spread_bps + cost_cfg.slippage_bps) / 10000.0

        n_sessions = len(calendar_sessions)

        # 4. Iterate chronologically through trading sessions
        for i, current_date in enumerate(calendar_sessions):
            # A. Process scheduled exits at current_date close
            # These are positions whose scheduled_exit_date <= current_date
            remaining_open_positions: List[PositionRecord] = []
            for pos in open_positions:
                if pos.scheduled_exit_date == current_date or (
                    pos.scheduled_exit_date is not None and pos.scheduled_exit_date < current_date
                ):
                    # Execute Exit at adjusted_close
                    exit_price = price_lookup.get((current_date, pos.ticker, "adjusted_close"))
                    if exit_price is None or not (exit_price > 0):
                        # Fail-safe fallback to last known close price
                        exit_price = pos.entry_price or 1.0

                    pos.exit_price = float(exit_price)
                    pos.actual_exit_date = current_date
                    gross_proceeds = pos.shares * pos.exit_price
                    exit_cost = gross_proceeds * one_way_exit_rate
                    pos.exit_cost = float(exit_cost)
                    pos.total_cost = float(pos.entry_cost + pos.exit_cost)

                    net_proceeds = gross_proceeds - exit_cost
                    cash += net_proceeds

                    realized_pnl = net_proceeds - (pos.allocated_capital + pos.entry_cost)
                    pos.realized_pnl = float(realized_pnl)
                    pos.net_return = float(realized_pnl / pos.allocated_capital) if pos.allocated_capital > 0 else 0.0
                    pos.status = PositionStatus.CLOSED

                    total_realized_pnl += realized_pnl
                    total_costs_incurred += exit_cost
                    closed_positions.append(pos)
                else:
                    remaining_open_positions.append(pos)

            open_positions = remaining_open_positions

            # B. Execute pending entry orders at current_date open
            remaining_pending: List[PositionRecord] = []
            for pos in pending_entries:
                if pos.entry_date == current_date:
                    entry_price = price_lookup.get((current_date, pos.ticker, "adjusted_open"))
                    if entry_price is None or not (entry_price > 0):
                        # Execution failed due to missing price data
                        pos.status = PositionStatus.REJECTED
                        pos.rejection_reason = OrderRejectionReason.MISSING_PRICE_DATA.value
                        cash += pos.allocated_capital  # Release reserved capital
                        rejected_orders.append(pos)
                        continue

                    pos.entry_price = float(entry_price)
                    # Compute exact shares (fractional shares supported for exact accounting)
                    shares = pos.allocated_capital / pos.entry_price
                    pos.shares = float(shares)

                    entry_cost = pos.allocated_capital * one_way_entry_rate
                    pos.entry_cost = float(entry_cost)
                    # Deduct entry cost from cash
                    cash -= entry_cost
                    total_costs_incurred += entry_cost

                    pos.status = PositionStatus.OPEN
                    open_positions.append(pos)
                else:
                    remaining_pending.append(pos)

            pending_entries = remaining_pending

            # C. Evaluate new candidate signals emitted on current_date
            todays_signals = decisions_by_date.get(current_date, [])
            for sig in todays_signals:
                action = str(sig.get("signal", "HOLD")).upper()
                ticker = str(sig.get("ticker", "")).upper()
                cid = str(sig.get("company_id", ""))

                if action == "BUY":
                    # Check next session for entry date
                    if i + 1 >= n_sessions:
                        # Cannot execute beyond terminal session
                        rej = PositionRecord(
                            position_id=f"POS_{ticker}_{current_date}_REJ",
                            ticker=ticker,
                            company_id=cid,
                            signal_date=current_date,
                            status=PositionStatus.REJECTED,
                            rejection_reason=OrderRejectionReason.MISSING_PRICE_DATA.value,
                        )
                        rejected_orders.append(rej)
                        continue

                    entry_date = calendar_sessions[i + 1]
                    # Holding horizon: H trading sessions -> exit at T+H close
                    exit_idx = min(i + self.config.holding_horizon_sessions, n_sessions - 1)
                    scheduled_exit_date = calendar_sessions[exit_idx]

                    # Check Portfolio Constraints
                    current_open_tickers = [p.ticker for p in open_positions] + [p.ticker for p in pending_entries]
                    total_concurrent = len(open_positions) + len(pending_entries)

                    # 1. Multiple positions per ticker constraint
                    if not self.config.allow_multiple_positions_per_ticker and ticker in current_open_tickers:
                        rej = PositionRecord(
                            position_id=f"POS_{ticker}_{current_date}_REJ",
                            ticker=ticker,
                            company_id=cid,
                            signal_date=current_date,
                            status=PositionStatus.REJECTED,
                            rejection_reason=OrderRejectionReason.MAX_TICKER_EXPOSURE.value,
                        )
                        rejected_orders.append(rej)
                        continue

                    # 2. Maximum concurrent positions constraint
                    if total_concurrent >= self.config.max_concurrent_positions:
                        rej = PositionRecord(
                            position_id=f"POS_{ticker}_{current_date}_REJ",
                            ticker=ticker,
                            company_id=cid,
                            signal_date=current_date,
                            status=PositionStatus.REJECTED,
                            rejection_reason=OrderRejectionReason.CONCURRENT_LIMIT_REACHED.value,
                        )
                        rejected_orders.append(rej)
                        continue

                    # 3. Available cash and sizing constraint
                    available_cash = cash - self.config.min_cash_reserve
                    if available_cash < self.config.min_order_amount:
                        rej = PositionRecord(
                            position_id=f"POS_{ticker}_{current_date}_REJ",
                            ticker=ticker,
                            company_id=cid,
                            signal_date=current_date,
                            status=PositionStatus.REJECTED,
                            rejection_reason=OrderRejectionReason.INSUFFICIENT_CASH.value,
                        )
                        rejected_orders.append(rej)
                        continue

                    # Target allocation size: min(max_weight * equity, available_cash)
                    max_dollar_allocation = self.config.max_position_weight * equity
                    allocation = min(max_dollar_allocation, available_cash)

                    # Aggregate exposure constraint
                    current_invested_val = sum(
                        p.shares * price_lookup.get((current_date, p.ticker, "adjusted_close"), p.entry_price or 0.0)
                        for p in open_positions
                    ) + sum(p.allocated_capital for p in pending_entries)

                    max_allowed_invested = self.config.max_aggregate_exposure * equity
                    if current_invested_val + allocation > max_allowed_invested:
                        allocation = max(0.0, max_allowed_invested - current_invested_val)

                    if allocation < self.config.min_order_amount:
                        rej = PositionRecord(
                            position_id=f"POS_{ticker}_{current_date}_REJ",
                            ticker=ticker,
                            company_id=cid,
                            signal_date=current_date,
                            status=PositionStatus.REJECTED,
                            rejection_reason=OrderRejectionReason.MAX_AGGREGATE_EXPOSURE.value,
                        )
                        rejected_orders.append(rej)
                        continue

                    # Reserve capital and queue pending entry
                    cash -= allocation
                    new_pos = PositionRecord(
                        position_id=f"POS_{ticker}_{entry_date}_{i}",
                        ticker=ticker,
                        company_id=cid,
                        signal_date=current_date,
                        entry_date=entry_date,
                        scheduled_exit_date=scheduled_exit_date,
                        allocated_capital=float(allocation),
                        status=PositionStatus.PENDING_ENTRY,
                    )
                    pending_entries.append(new_pos)

                elif action == "SELL":
                    # In long-only research mode, SELL does not open short positions
                    # Explicitly documented invariant
                    pass
                else:  # HOLD
                    pass

            # D. Mark-to-Market Valuation at current_date close
            invested_val = 0.0
            for pos in open_positions:
                cur_close = price_lookup.get((current_date, pos.ticker, "adjusted_close"))
                if cur_close is None or not (cur_close > 0):
                    cur_close = pos.entry_price or 1.0
                invested_val += pos.shares * cur_close

            # Pending entries capital is committed in cash reservation
            total_invested_capital = invested_val + sum(p.allocated_capital for p in pending_entries)
            equity = cash + total_invested_capital
            peak_equity = max(peak_equity, equity)

            prev_equity = daily_history[-1].portfolio_equity if daily_history else self.config.initial_cash
            daily_ret = (equity - prev_equity) / prev_equity if prev_equity > 0 else 0.0
            cum_ret = (equity - self.config.initial_cash) / self.config.initial_cash
            dd = (equity - peak_equity) / peak_equity if peak_equity > 0 else 0.0
            utilization = total_invested_capital / equity if equity > 0 else 0.0

            snapshot = DailyPortfolioSnapshot(
                date=current_date,
                cash=float(cash),
                invested_capital=float(total_invested_capital),
                portfolio_equity=float(equity),
                daily_return=float(daily_ret),
                cumulative_return=float(cum_ret),
                open_positions_count=len(open_positions) + len(pending_entries),
                capital_utilization=float(utilization),
                drawdown=float(dd),
                total_realized_pnl=float(total_realized_pnl),
                total_transaction_costs=float(total_costs_incurred),
            )
            daily_history.append(snapshot)

        # 5. Compute summary statistics
        return self._compute_summary_metrics(
            strategy_name=strategy_name,
            daily_history=daily_history,
            closed_positions=closed_positions,
            rejected_orders=rejected_orders,
            total_costs=total_costs_incurred,
        )

    def _prepare_market_pricing(
        self, market_df: pd.DataFrame
    ) -> Tuple[Dict[Tuple[str, str, str], float], List[str]]:
        """Pre-indexes adjusted open and close prices for rapid deterministic lookup."""
        df = market_df.copy()
        if "adjusted_open" not in df.columns:
            adj_factor = df["adjusted_close"] / df["close"]
            df["adjusted_open"] = df["open"] * adj_factor

        calendar_sessions = sorted(df["trading_date"].unique().tolist())
        price_lookup: Dict[Tuple[str, str, str], float] = {}

        for _, row in df.iterrows():
            d = str(row["trading_date"])
            t = str(row["ticker"])
            adj_open = float(row["adjusted_open"])
            adj_close = float(row["adjusted_close"])
            price_lookup[(d, t, "adjusted_open")] = adj_open
            price_lookup[(d, t, "adjusted_close")] = adj_close

        return price_lookup, calendar_sessions

    def _prepare_decisions_map(self, decisions_df: pd.DataFrame) -> Dict[str, List[Dict[str, Any]]]:
        """Groups candidate signals by decision trading date."""
        if decisions_df.empty:
            return {}
        dec_map: Dict[str, List[Dict[str, Any]]] = {}
        for d, grp in decisions_df.groupby("trading_date"):
            dec_map[str(d)] = grp.to_dict(orient="records")
        return dec_map

    def _compute_summary_metrics(
        self,
        strategy_name: str,
        daily_history: List[DailyPortfolioSnapshot],
        closed_positions: List[PositionRecord],
        rejected_orders: List[PositionRecord],
        total_costs: float,
    ) -> PortfolioSimulationResult:
        """Derives standard institutional metrics from daily snapshots and closed positions."""
        init_eq = float(self.config.initial_cash)
        final_eq = daily_history[-1].portfolio_equity if daily_history else init_eq
        total_ret = (final_eq - init_eq) / init_eq

        daily_returns = np.array([s.daily_return for s in daily_history])
        n_days = len(daily_returns)
        ann_factor = 252.0

        # Annualized return
        if n_days > 0 and final_eq > 0:
            ann_ret = float((final_eq / init_eq) ** (ann_factor / n_days) - 1.0)
        else:
            ann_ret = 0.0

        # Max drawdown
        drawdowns = [s.drawdown for s in daily_history]
        max_dd = float(min(drawdowns)) if drawdowns else 0.0

        # Volatility and Sharpe
        if n_days > 1 and np.std(daily_returns) > 0:
            daily_vol = float(np.std(daily_returns, ddof=1) * np.sqrt(ann_factor))
            mean_daily = float(np.mean(daily_returns))
            sharpe = float((mean_daily / np.std(daily_returns, ddof=1)) * np.sqrt(ann_factor))
        else:
            daily_vol = 0.0
            sharpe = 0.0

        # Trade metrics
        n_closed = len(closed_positions)
        if n_closed > 0:
            trade_rets = [p.net_return for p in closed_positions if p.net_return is not None]
            win_count = sum(1 for r in trade_rets if r > 0)
            loss_count = sum(1 for r in trade_rets if r <= 0)
            win_rate = float(win_count / n_closed)
            mean_trade_ret = float(np.mean(trade_rets))
            median_trade_ret = float(np.median(trade_rets))
        else:
            win_count = 0
            loss_count = 0
            win_rate = 0.0
            mean_trade_ret = 0.0
            median_trade_ret = 0.0

        # Utilization and Concurrent stats
        utils = [s.capital_utilization for s in daily_history]
        concur = [s.open_positions_count for s in daily_history]
        avg_util = float(np.mean(utils)) if utils else 0.0
        max_util = float(max(utils)) if utils else 0.0
        avg_concur = float(np.mean(concur)) if concur else 0.0
        max_concur = int(max(concur)) if concur else 0

        # Rejection breakdown
        rejection_breakdown: Dict[str, int] = {}
        for rej in rejected_orders:
            reason = rej.rejection_reason or "UNKNOWN"
            rejection_breakdown[reason] = rejection_breakdown.get(reason, 0) + 1

        return PortfolioSimulationResult(
            strategy_name=strategy_name,
            initial_equity=init_eq,
            final_equity=final_eq,
            total_net_return=total_ret,
            annualized_return=ann_ret,
            max_drawdown=max_dd,
            daily_volatility=daily_vol,
            sharpe_ratio=sharpe,
            risk_free_rate_assumed=0.0,
            total_closed_trades=n_closed,
            winning_trades=win_count,
            losing_trades=loss_count,
            win_rate=win_rate,
            mean_net_return_per_trade=mean_trade_ret,
            median_net_return_per_trade=median_trade_ret,
            mean_holding_duration_days=float(self.config.holding_horizon_sessions),
            total_transaction_costs=float(total_costs),
            total_rejected_orders=len(rejected_orders),
            rejection_breakdown=rejection_breakdown,
            average_utilization=avg_util,
            max_utilization=max_util,
            average_concurrent_positions=avg_concur,
            max_concurrent_positions=max_concur,
            daily_history=daily_history,
            closed_positions=closed_positions,
            rejected_orders=rejected_orders,
        )

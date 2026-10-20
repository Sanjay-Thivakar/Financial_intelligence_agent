"""
Portfolio Simulation and Rolling Threshold Validation Schemas (Phase 5H).

Defines typed interfaces, configuration models, position tracking records,
and accounting snapshots for deterministic portfolio execution and leakage-free threshold tuning.
"""

from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from src.decision.schema import TransactionCostConfig


class PositionStatus(str, Enum):
    """Lifecycle state of a simulated trading position."""
    PENDING_ENTRY = "PENDING_ENTRY"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    REJECTED = "REJECTED"


class OrderRejectionReason(str, Enum):
    """Reason why a candidate decision signal could not be funded/opened in the portfolio."""
    CONCURRENT_LIMIT_REACHED = "CONCURRENT_LIMIT_REACHED"
    MAX_TICKER_EXPOSURE = "MAX_TICKER_EXPOSURE"
    INSUFFICIENT_CASH = "INSUFFICIENT_CASH"
    MAX_AGGREGATE_EXPOSURE = "MAX_AGGREGATE_EXPOSURE"
    MISSING_PRICE_DATA = "MISSING_PRICE_DATA"
    INVALID_SIGNAL = "INVALID_SIGNAL"
    BELOW_MIN_ORDER_AMOUNT = "BELOW_MIN_ORDER_AMOUNT"


class PortfolioConfig(BaseModel):
    """
    Configurable portfolio constraints and capital allocation rules.
    """
    initial_cash: float = Field(100_000.0, gt=0.0, description="Starting cash capital in USD")
    max_concurrent_positions: int = Field(4, ge=1, description="Maximum number of simultaneous open positions")
    max_position_weight: float = Field(0.25, gt=0.0, le=1.0, description="Maximum target weight per position (e.g. 0.25 = 25%)")
    max_aggregate_exposure: float = Field(1.0, gt=0.0, le=1.0, description="Maximum total portfolio exposure fraction (1.0 = 100%, no leverage)")
    min_cash_reserve: float = Field(0.0, ge=0.0, description="Mandatory minimum uninvested cash buffer in USD")
    holding_horizon_sessions: int = Field(5, ge=1, description="Fixed holding duration in trading sessions (T+1 open to T+5 close)")
    allow_multiple_positions_per_ticker: bool = Field(False, description="Whether to allow overlapping positions in the same asset")
    min_order_amount: float = Field(100.0, ge=1.0, description="Minimum order size in USD to prevent trivial allocations")
    cost_config: TransactionCostConfig = Field(default_factory=TransactionCostConfig, description="Institutional fee and slippage model")


class PositionRecord(BaseModel):
    """
    Complete lifecycle audit trail for an individual position.
    """
    position_id: str
    ticker: str
    company_id: str
    signal_date: str
    entry_date: Optional[str] = None
    scheduled_exit_date: Optional[str] = None
    actual_exit_date: Optional[str] = None
    shares: float = 0.0
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    allocated_capital: float = 0.0
    entry_cost: float = 0.0
    exit_cost: float = 0.0
    total_cost: float = 0.0
    realized_pnl: Optional[float] = None
    net_return: Optional[float] = None
    status: PositionStatus = PositionStatus.PENDING_ENTRY
    rejection_reason: Optional[str] = None


class DailyPortfolioSnapshot(BaseModel):
    """
    Daily mark-to-market snapshot of portfolio state.
    """
    date: str
    cash: float
    invested_capital: float
    portfolio_equity: float
    daily_return: float
    cumulative_return: float
    open_positions_count: int
    capital_utilization: float
    drawdown: float
    total_realized_pnl: float
    total_transaction_costs: float


class PortfolioSimulationResult(BaseModel):
    """
    Comprehensive performance and audit metrics from a portfolio simulation run.
    """
    strategy_name: str
    initial_equity: float
    final_equity: float
    total_net_return: float
    annualized_return: Optional[float]
    max_drawdown: float
    daily_volatility: Optional[float]
    sharpe_ratio: Optional[float]
    risk_free_rate_assumed: float = 0.0
    total_closed_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    mean_net_return_per_trade: float
    median_net_return_per_trade: float
    mean_holding_duration_days: float
    total_transaction_costs: float
    total_rejected_orders: int
    rejection_breakdown: Dict[str, int] = Field(default_factory=dict)
    average_utilization: float
    max_utilization: float
    average_concurrent_positions: float
    max_concurrent_positions: int
    daily_history: List[DailyPortfolioSnapshot] = Field(default_factory=list)
    closed_positions: List[PositionRecord] = Field(default_factory=list)
    rejected_orders: List[PositionRecord] = Field(default_factory=list)


class RollingThresholdConfig(BaseModel):
    """
    Configuration for leakage-safe chronological threshold selection.
    """
    candidate_thresholds: List[float] = Field(
        default_factory=lambda: [0.005, 0.010, 0.015, 0.020, 0.030],
        description="Candidate directional thresholds to evaluate"
    )
    inner_val_sessions: int = Field(45, ge=10, description="Sessions for inner validation window")
    inner_purge_sessions: int = Field(5, ge=1, description="Purge gap between inner train and inner val")
    min_inner_trades: int = Field(3, ge=1, description="Minimum trades required on inner validation to avoid fallback")
    fallback_threshold: float = Field(0.015, description="Conservative default threshold when inner evidence is sparse")


class RollingThresholdResult(BaseModel):
    """
    Result metadata for an outer fold's threshold selection.
    """
    outer_fold: int
    selected_threshold: float
    fallback_used: bool
    fallback_reason: Optional[str] = None
    inner_val_trade_counts: Dict[str, int] = Field(default_factory=dict)
    inner_val_net_returns: Dict[str, float] = Field(default_factory=dict)
    inner_train_dates: Optional[str] = None
    inner_val_dates: Optional[str] = None

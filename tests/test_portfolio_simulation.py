"""
Unit and Integration Tests for Phase 5H Portfolio Simulation and Rolling Threshold Selection.

Verifies:
1. Conservation of capital and portfolio equity reconciliation.
2. Entry and exit transaction cost deductions.
3. Concurrent position limits and allocation constraints.
4. Overlapping 5-session position lifecycle and capital release.
5. Rejection mechanics for insufficient cash, max exposure, or missing prices.
6. Rolling threshold selection chronological isolation and minimum-evidence fallback.
7. Simulation determinism.
"""

import pytest
import numpy as np
import pandas as pd

from src.decision.schema import TransactionCostConfig
from src.portfolio.schema import (
    PortfolioConfig,
    PositionStatus,
    OrderRejectionReason,
    RollingThresholdConfig,
)
from src.portfolio.simulator import DeterministicPortfolioSimulator
from src.portfolio.rolling import RollingThresholdSelector


@pytest.fixture
def synthetic_market_data():
    """Generates 30 trading sessions of synthetic market prices for AAPL, MSFT, GOOG."""
    dates = pd.date_range("2020-01-01", periods=30, freq="B").strftime("%Y-%m-%d").tolist()
    records = []
    for d_idx, d in enumerate(dates):
        for ticker in ["AAPL", "MSFT", "GOOG"]:
            base_price = 100.0 + (10.0 if ticker == "AAPL" else 20.0 if ticker == "MSFT" else 30.0)
            # Slight price drift
            p_open = base_price + d_idx * 0.5
            p_close = p_open + 0.25
            records.append({
                "trading_date": d,
                "ticker": ticker,
                "company_id": f"CID_{ticker}",
                "open": p_open,
                "close": p_close,
                "adjusted_close": p_close,
                "adjusted_open": p_open,
                "volume": 1_000_000,
            })
    return pd.DataFrame(records)


def test_portfolio_initial_equity_and_conservation(synthetic_market_data):
    """Verify that portfolio equity equals cash + invested capital across all sessions."""
    dates = sorted(synthetic_market_data["trading_date"].unique())
    # One BUY signal on day 0
    decisions = pd.DataFrame([{
        "trading_date": dates[0],
        "ticker": "AAPL",
        "company_id": "CID_AAPL",
        "signal": "BUY",
        "expected_net_return": 0.02,
    }])

    cfg = PortfolioConfig(
        initial_cash=100_000.0,
        max_concurrent_positions=4,
        max_position_weight=0.25,
        holding_horizon_sessions=5,
    )
    simulator = DeterministicPortfolioSimulator(cfg)
    result = simulator.simulate(decisions, synthetic_market_data, strategy_name="TestConservation")

    assert result.initial_equity == 100_000.0
    assert len(result.daily_history) == len(dates)

    # Invariance check: for every snapshot, equity == cash + invested_capital
    for snap in result.daily_history:
        assert np.isclose(snap.portfolio_equity, snap.cash + snap.invested_capital, atol=1e-4)


def test_portfolio_transaction_costs_deduction(synthetic_market_data):
    """Verify transaction costs are deducted at entry and exit."""
    dates = sorted(synthetic_market_data["trading_date"].unique())
    decisions = pd.DataFrame([{
        "trading_date": dates[0],
        "ticker": "AAPL",
        "company_id": "CID_AAPL",
        "signal": "BUY",
        "expected_net_return": 0.02,
    }])

    cost_cfg = TransactionCostConfig(
        entry_fee_bps=2.5,
        exit_fee_bps=2.5,
        half_spread_bps=2.5,
        slippage_bps=2.5,  # 15 bps round-trip = 7.5 bps one-way
    )
    cfg = PortfolioConfig(
        initial_cash=100_000.0,
        max_position_weight=0.25,  # $25,000 allocated
        cost_config=cost_cfg,
        holding_horizon_sessions=5,
    )
    simulator = DeterministicPortfolioSimulator(cfg)
    result = simulator.simulate(decisions, synthetic_market_data)

    assert len(result.closed_positions) == 1
    pos = result.closed_positions[0]
    assert pos.status == PositionStatus.CLOSED
    assert pos.entry_cost > 0
    assert pos.exit_cost > 0
    assert pos.total_cost == pos.entry_cost + pos.exit_cost
    assert result.total_transaction_costs == pos.total_cost


def test_concurrent_position_limits(synthetic_market_data):
    """Verify that orders exceeding max_concurrent_positions are rejected."""
    dates = sorted(synthetic_market_data["trading_date"].unique())
    # 3 BUY signals on day 0, but max_concurrent_positions = 2
    decisions = pd.DataFrame([
        {"trading_date": dates[0], "ticker": "AAPL", "company_id": "CID_AAPL", "signal": "BUY"},
        {"trading_date": dates[0], "ticker": "MSFT", "company_id": "CID_MSFT", "signal": "BUY"},
        {"trading_date": dates[0], "ticker": "GOOG", "company_id": "CID_GOOG", "signal": "BUY"},
    ])

    cfg = PortfolioConfig(
        initial_cash=100_000.0,
        max_concurrent_positions=2,  # Only 2 allowed
        max_position_weight=0.25,
    )
    simulator = DeterministicPortfolioSimulator(cfg)
    result = simulator.simulate(decisions, synthetic_market_data)

    assert len(result.closed_positions) == 2
    assert len(result.rejected_orders) == 1
    assert result.rejected_orders[0].rejection_reason == OrderRejectionReason.CONCURRENT_LIMIT_REACHED.value


def test_multiple_positions_per_ticker_disallowed(synthetic_market_data):
    """Verify that multiple simultaneous positions in the same ticker are rejected when disabled."""
    dates = sorted(synthetic_market_data["trading_date"].unique())
    # BUY AAPL on day 0, then BUY AAPL again on day 1 (while day 0 trade is still active)
    decisions = pd.DataFrame([
        {"trading_date": dates[0], "ticker": "AAPL", "company_id": "CID_AAPL", "signal": "BUY"},
        {"trading_date": dates[1], "ticker": "AAPL", "company_id": "CID_AAPL", "signal": "BUY"},
    ])

    cfg = PortfolioConfig(
        initial_cash=100_000.0,
        max_concurrent_positions=4,
        allow_multiple_positions_per_ticker=False,
    )
    simulator = DeterministicPortfolioSimulator(cfg)
    result = simulator.simulate(decisions, synthetic_market_data)

    assert len(result.closed_positions) == 1
    assert len(result.rejected_orders) == 1
    assert result.rejected_orders[0].rejection_reason == OrderRejectionReason.MAX_TICKER_EXPOSURE.value


def test_capital_release_after_exit(synthetic_market_data):
    """Verify capital is fully returned to cash after scheduled exit, allowing new trades."""
    dates = sorted(synthetic_market_data["trading_date"].unique())
    # Day 0: BUY AAPL with 5-session hold -> exits on Day 5
    # Day 6: BUY MSFT (should be accepted because AAPL closed and released capital)
    decisions = pd.DataFrame([
        {"trading_date": dates[0], "ticker": "AAPL", "company_id": "CID_AAPL", "signal": "BUY"},
        {"trading_date": dates[6], "ticker": "MSFT", "company_id": "CID_MSFT", "signal": "BUY"},
    ])

    cfg = PortfolioConfig(
        initial_cash=100_000.0,
        max_concurrent_positions=1,  # Only 1 concurrent position allowed
        holding_horizon_sessions=5,
    )
    simulator = DeterministicPortfolioSimulator(cfg)
    result = simulator.simulate(decisions, synthetic_market_data)

    assert len(result.closed_positions) == 2
    assert len(result.rejected_orders) == 0


def test_simulation_determinism(synthetic_market_data):
    """Verify identical inputs yield identical simulation results."""
    dates = sorted(synthetic_market_data["trading_date"].unique())
    decisions = pd.DataFrame([
        {"trading_date": dates[0], "ticker": "AAPL", "company_id": "CID_AAPL", "signal": "BUY"},
        {"trading_date": dates[2], "ticker": "MSFT", "company_id": "CID_MSFT", "signal": "BUY"},
    ])
    cfg = PortfolioConfig(initial_cash=100_000.0)

    sim1 = DeterministicPortfolioSimulator(cfg).simulate(decisions, synthetic_market_data)
    sim2 = DeterministicPortfolioSimulator(cfg).simulate(decisions, synthetic_market_data)

    assert sim1.final_equity == sim2.final_equity
    assert sim1.total_net_return == sim2.total_net_return
    assert len(sim1.closed_positions) == len(sim2.closed_positions)


def test_rolling_threshold_fallback_on_sparse_evidence():
    """Verify rolling threshold selector uses conservative fallback when inner validation has insufficient trades."""
    # Synthetic dataset with too few dates or zero trade opportunities
    dates = pd.date_range("2019-01-01", periods=60, freq="B").strftime("%Y-%m-%d").tolist()
    records = []
    for d in dates:
        records.append({
            "trading_date": d,
            "ticker": "AAPL",
            "company_id": "CID_AAPL",
            "market_return_1d": 0.001,
            "target_forward_return_5d": 0.002,
            "market_volatility_5d": 0.05,
        })
    df_train = pd.DataFrame(records)

    cfg = RollingThresholdConfig(
        inner_val_sessions=20,
        inner_purge_sessions=5,
        min_inner_trades=5,
        fallback_threshold=0.015,
    )
    selector = RollingThresholdSelector(cfg)
    res = selector.select_threshold_for_fold(
        outer_fold=0,
        df_train_outer=df_train,
        feature_columns=["market_return_1d"],
        base_cost_cfg=TransactionCostConfig(),
    )

    # Because model won't produce 5 trades clearing thresholds on calm synthetic data, fallback must trigger
    assert res.fallback_used is True
    assert res.selected_threshold == 0.015
    assert "Sparse inner validation evidence" in res.fallback_reason or "Insufficient historical dates" in res.fallback_reason


def test_portfolio_missing_price_handling():
    """Verify missing execution prices trigger fail-safe rejection without crashing or leaking capital."""
    dates = ["2020-01-02", "2020-01-03", "2020-01-06"]
    # AAPL has pricing on Day 0 and Day 2, but missing on Day 1 (the scheduled entry date).
    # MSFT has prices on all 3 days, establishing the trading calendar.
    market = pd.DataFrame([
        {"trading_date": dates[0], "ticker": "AAPL", "company_id": "CID_AAPL", "open": 100.0, "close": 101.0, "adjusted_close": 101.0, "adjusted_open": 100.0},
        {"trading_date": dates[2], "ticker": "AAPL", "company_id": "CID_AAPL", "open": 105.0, "close": 106.0, "adjusted_close": 106.0, "adjusted_open": 105.0},
        {"trading_date": dates[0], "ticker": "MSFT", "company_id": "CID_MSFT", "open": 200.0, "close": 201.0, "adjusted_close": 201.0, "adjusted_open": 200.0},
        {"trading_date": dates[1], "ticker": "MSFT", "company_id": "CID_MSFT", "open": 202.0, "close": 203.0, "adjusted_close": 203.0, "adjusted_open": 202.0},
        {"trading_date": dates[2], "ticker": "MSFT", "company_id": "CID_MSFT", "open": 204.0, "close": 205.0, "adjusted_close": 205.0, "adjusted_open": 204.0},
    ])
    decisions = pd.DataFrame([
        {"trading_date": dates[0], "ticker": "AAPL", "company_id": "CID_AAPL", "signal": "BUY"},
    ])

    cfg = PortfolioConfig(initial_cash=100_000.0)
    sim = DeterministicPortfolioSimulator(cfg).simulate(decisions, market)

    assert len(sim.rejected_orders) == 1
    assert sim.rejected_orders[0].rejection_reason == OrderRejectionReason.MISSING_PRICE_DATA.value
    # Capital must remain intact
    assert sim.final_equity == 100_000.0


def test_aggregate_exposure_constraint(synthetic_market_data):
    """Verify max_aggregate_exposure limits total invested dollars."""
    dates = sorted(synthetic_market_data["trading_date"].unique())
    # 3 BUY signals, but max_aggregate_exposure is 40% ($40,000 max) and each wants 25% ($25,000)
    decisions = pd.DataFrame([
        {"trading_date": dates[0], "ticker": "AAPL", "company_id": "CID_AAPL", "signal": "BUY"},
        {"trading_date": dates[0], "ticker": "MSFT", "company_id": "CID_MSFT", "signal": "BUY"},
        {"trading_date": dates[0], "ticker": "GOOG", "company_id": "CID_GOOG", "signal": "BUY"},
    ])

    cfg = PortfolioConfig(
        initial_cash=100_000.0,
        max_concurrent_positions=4,
        max_position_weight=0.25,
        max_aggregate_exposure=0.40,  # 40% cap ($40k)
    )
    sim = DeterministicPortfolioSimulator(cfg).simulate(decisions, synthetic_market_data)

    # AAPL takes $25k. MSFT takes min($25k, $40k-$25k) = $15k. GOOG has remaining $0 < $100 -> rejected.
    assert len(sim.closed_positions) == 2
    assert len(sim.rejected_orders) == 1
    assert sim.rejected_orders[0].rejection_reason == OrderRejectionReason.MAX_AGGREGATE_EXPOSURE.value
    assert sim.max_utilization <= 0.405


def test_api_portfolio_research_endpoint():
    """Verify GET /api/models/portfolio/research endpoint returns 200 and Phase 5H artifacts."""
    from fastapi.testclient import TestClient
    from src.api.app import app

    client = TestClient(app)
    resp = client.get("/api/models/portfolio/research")
    assert resp.status_code == 200
    data = resp.json()
    assert "strategy_results" in data
    assert "cash_benchmark" in data["strategy_results"]
    assert "buy_and_hold_benchmark" in data["strategy_results"]
    assert "fixed_threshold_policy" in data["strategy_results"]
    assert "rolling_threshold_policy" in data["strategy_results"]
    assert "rolling_threshold_selection" in data


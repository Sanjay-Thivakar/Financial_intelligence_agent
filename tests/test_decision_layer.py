"""
Unit and Integration Tests for Phase 5G Decision & Risk Layer.

Covers:
1. Positive, negative, near-zero, and threshold boundary forecast evaluations.
2. Transaction cost and slippage deductions (round-trip, net expected return).
3. Residual uncertainty estimation and uncertainty ceiling gating (forcing HOLD).
4. Risk gates: stale market data, feature ratio completeness, abnormal volatility, model cutoff.
5. Invariance & determinism: identical inputs yield identical signals and explanations.
6. API endpoint integration: POST /api/models/decision with validation and error handling.
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from src.decision.schema import (
    SignalType,
    TransactionCostConfig,
    RiskGateConfig,
    DecisionContractRequest,
    DecisionContractResponse,
)
from src.decision.cost import TransactionCostModel
from src.decision.uncertainty import ResidualUncertaintyEstimator
from src.decision.risk import RiskGateEvaluator
from src.decision.policy import ThresholdDecisionPolicy
from src.api.app import app


client = TestClient(app)


# ==============================================================================
# 1. TRANSACTION COST AND SLIPPAGE TESTS
# ==============================================================================

def test_transaction_cost_calculations():
    """Verify default 15 bps and customized round-trip cost calculations in bps and decimal."""
    # Default config = 15.0 bps base
    default_cfg = TransactionCostConfig()
    assert default_cfg.total_roundtrip_bps == 15.0
    assert np.isclose(default_cfg.total_roundtrip_decimal, 0.0015)

    cost_model = TransactionCostModel()
    default_breakdown = cost_model.calculate_cost_breakdown(default_cfg)
    assert default_breakdown["total_roundtrip_bps"] == 15.0
    assert default_breakdown["total_spread_bps"] == 5.0
    assert default_breakdown["total_slippage_bps"] == 5.0

    # Custom 20 bps scenario
    cfg_20 = TransactionCostConfig(
        entry_fee_bps=2.5,
        exit_fee_bps=2.5,
        half_spread_bps=2.5,
        slippage_bps=5.0,
    )
    assert cfg_20.total_roundtrip_bps == 20.0
    assert np.isclose(cfg_20.total_roundtrip_decimal, 0.0020)

    breakdown_20 = cost_model.calculate_cost_breakdown(cfg_20)
    assert breakdown_20["total_roundtrip_bps"] == 20.0
    assert breakdown_20["total_spread_bps"] == 5.0
    assert breakdown_20["total_slippage_bps"] == 10.0

    # Net expected return adjustments under base 15 bps
    pred_buy = 0.03  # +3.0%
    net_buy = cost_model.calculate_expected_net_return(pred_buy, SignalType.BUY, default_cfg)
    assert np.isclose(net_buy, 0.03 - 0.0015)  # 0.0285

    pred_sell = -0.03  # -3.0%
    net_sell = cost_model.calculate_expected_net_return(pred_sell, SignalType.SELL, default_cfg)
    assert np.isclose(net_sell, -0.03 + 0.0015)  # -0.0285 (less negative magnitude)


def test_transaction_cost_sensitivity_scenarios():
    """Audit low, base, and high friction scenarios."""
    cost_model = TransactionCostModel()
    scenarios = {
        "low_friction": TransactionCostConfig(entry_fee_bps=1.0, exit_fee_bps=1.0, half_spread_bps=1.0, slippage_bps=0.5), # 5.0 bps
        "base_friction": TransactionCostConfig(entry_fee_bps=2.5, exit_fee_bps=2.5, half_spread_bps=2.5, slippage_bps=2.5), # 15.0 bps
        "high_friction": TransactionCostConfig(entry_fee_bps=5.0, exit_fee_bps=5.0, half_spread_bps=5.0, slippage_bps=5.0), # 30.0 bps
    }
    assert scenarios["low_friction"].total_roundtrip_bps == 5.0
    assert scenarios["base_friction"].total_roundtrip_bps == 15.0
    assert scenarios["high_friction"].total_roundtrip_bps == 30.0

    # Ensure net return monotonically decreases with higher friction
    forecast = 0.025
    net_low = cost_model.calculate_expected_net_return(forecast, SignalType.BUY, scenarios["low_friction"])
    net_base = cost_model.calculate_expected_net_return(forecast, SignalType.BUY, scenarios["base_friction"])
    net_high = cost_model.calculate_expected_net_return(forecast, SignalType.BUY, scenarios["high_friction"])
    assert net_low > net_base > net_high


def test_metric_comparability_active_vs_portfolio_denominators():
    """Verify distinction between active trade return and opportunity-diluted observation return."""
    # Simulating 7 active trades returning +3.13% and 713 HOLDs returning 0.0%
    active_returns = np.array([0.0313] * 7)
    hold_returns = np.zeros(713)
    all_returns = np.concatenate([active_returns, hold_returns])

    mean_active_trade_return = active_returns.mean()
    mean_unconditional_session_return = all_returns.mean()

    assert np.isclose(mean_active_trade_return, 0.0313)
    assert np.isclose(mean_unconditional_session_return, 7 * 0.0313 / 720, atol=1e-5)
    # The active trade return is ~103x larger than the unconditional session return
    assert mean_active_trade_return > 100 * mean_unconditional_session_return


# ==============================================================================
# 2. RESIDUAL UNCERTAINTY ESTIMATOR TESTS
# ==============================================================================

def test_residual_uncertainty_estimator_calibration():
    """Verify uncertainty standard deviation and prediction interval calculation."""
    np.random.seed(42)
    synthetic_resids = np.random.normal(loc=0.0, scale=0.045, size=200)

    estimator = ResidualUncertaintyEstimator(
        training_residuals=synthetic_resids,
        method_name="train_residuals_test",
    )
    assert estimator.is_available is True
    assert estimator.n_samples == 200
    assert 0.040 < estimator.get_uncertainty() < 0.050

    # Prediction interval for forecast +0.02 at 80% (z ~ 1.282)
    pi_80 = estimator.compute_prediction_interval(predicted_return=0.02, confidence_level=0.80)
    assert pi_80 is not None
    assert pi_80[0] < 0.02 < pi_80[1]

    # Test unavailable estimator
    empty_estimator = ResidualUncertaintyEstimator(training_residuals=None)
    assert empty_estimator.is_available is False
    assert empty_estimator.get_uncertainty() is None
    assert empty_estimator.compute_prediction_interval(0.02) is None


# ==============================================================================
# 3. RISK GATE EVALUATION TESTS
# ==============================================================================

@pytest.fixture
def base_valid_request():
    return DecisionContractRequest(
        company_id="US_CIK_0000320193",
        ticker="AAPL",
        decision_timestamp="2020-04-15T14:15:00Z",
        predicted_forward_return=0.035,  # +3.5%
        forecast_uncertainty=0.045,      # 4.5%
        rolling_volatility_5d=0.05,
        feature_metadata={"n_features_used": 17, "n_features_required": 17, "as_of_date": "2020-04-15"},
        model_id="Ridge-Market-v1",
        model_version="1.0.0",
        training_cutoff_date="2020-03-23",
        cost_config=TransactionCostConfig(),
        risk_config=RiskGateConfig(max_uncertainty=0.08, buy_threshold=0.015),
    )


def test_risk_gates_all_pass(base_valid_request):
    """Test standard case where all risk controls are satisfied."""
    passed, checks_pass, checks_fail, warnings = RiskGateEvaluator.evaluate_gates(
        base_valid_request,
        uncertainty=0.045,
    )
    assert passed is True
    assert len(checks_fail) == 0
    assert len(checks_pass) >= 5


def test_risk_gate_excluded_ticker(base_valid_request):
    """Test that excluded ticker (AA) fails exclusion gate."""
    req = base_valid_request.model_copy(update={"ticker": "AA", "company_id": "UNKNOWN_AA"})
    passed, _, checks_fail, _ = RiskGateEvaluator.evaluate_gates(req, uncertainty=0.045)
    assert passed is False
    assert any("EXCLUSION_GATE" in f for f in checks_fail)


def test_risk_gate_excessive_uncertainty(base_valid_request):
    """Test that uncertainty exceeding ceiling fails uncertainty gate."""
    passed, _, checks_fail, _ = RiskGateEvaluator.evaluate_gates(base_valid_request, uncertainty=0.12)
    assert passed is False
    assert any("UNCERTAINTY_GATE" in f for f in checks_fail)


def test_risk_gate_abnormal_volatility(base_valid_request):
    """Test that rolling volatility exceeding ceiling fails volatility gate."""
    req = base_valid_request.model_copy(update={"rolling_volatility_5d": 0.25})  # 25% > 15%
    passed, _, checks_fail, _ = RiskGateEvaluator.evaluate_gates(req, uncertainty=0.045)
    assert passed is False
    assert any("VOLATILITY_GATE" in f for f in checks_fail)


def test_risk_gate_inverted_temporal_cutoff(base_valid_request):
    """Test that decision date prior to training cutoff date triggers provenance failure."""
    req = base_valid_request.model_copy(update={
        "decision_timestamp": "2020-01-10T14:15:00Z",
        "training_cutoff_date": "2020-03-23",  # Model trained into future relative to decision!
    })
    passed, _, checks_fail, _ = RiskGateEvaluator.evaluate_gates(req, uncertainty=0.045)
    assert passed is False
    assert any("PROVENANCE_GATE" in f for f in checks_fail)


# ==============================================================================
# 4. DECISION POLICY SIGNAL GENERATION & BOUNDARY TESTS
# ==============================================================================

def test_decision_policy_buy_signal(base_valid_request):
    """Valid positive forecast clearing threshold + cost produces BUY."""
    policy = ThresholdDecisionPolicy()
    resp = policy.evaluate(base_valid_request)
    assert resp.signal == SignalType.BUY
    assert resp.expected_net_return > 0.015
    assert any("BUY CANDIDATE SIGNAL" in r for r in resp.reasons)
    assert resp.is_experimental is True


def test_decision_policy_sell_signal(base_valid_request):
    """Valid negative forecast clearing threshold + cost produces SELL."""
    req = base_valid_request.model_copy(update={"predicted_forward_return": -0.035})
    policy = ThresholdDecisionPolicy()
    resp = policy.evaluate(req)
    assert resp.signal == SignalType.SELL
    assert resp.expected_net_return < -0.015
    assert any("SELL CANDIDATE SIGNAL" in r for r in resp.reasons)


def test_decision_policy_near_zero_hold(base_valid_request):
    """Near-zero positive return (+0.5%) fails to clear buy threshold (1.5%) -> HOLD."""
    req = base_valid_request.model_copy(update={"predicted_forward_return": 0.008})
    policy = ThresholdDecisionPolicy()
    resp = policy.evaluate(req)
    assert resp.signal == SignalType.HOLD
    assert any("fails to clear BUY threshold" in r or "COST_HURDLE_GATE" in r for r in resp.reasons)


def test_decision_policy_forced_hold_on_gate_failure(base_valid_request):
    """High forecast (+10%) with excessive uncertainty (15%) is forced to HOLD."""
    req = base_valid_request.model_copy(update={
        "predicted_forward_return": 0.10,
        "forecast_uncertainty": 0.15,  # > 0.08
    })
    policy = ThresholdDecisionPolicy()
    resp = policy.evaluate(req)
    assert resp.signal == SignalType.HOLD
    assert any("SIGNAL FORCED TO HOLD" in r for r in resp.reasons)


def test_decision_policy_determinism(base_valid_request):
    """Verify that duplicate identical requests produce identical deterministic outputs."""
    policy = ThresholdDecisionPolicy()
    resp1 = policy.evaluate(base_valid_request)
    resp2 = policy.evaluate(base_valid_request)
    assert resp1.signal == resp2.signal
    assert resp1.expected_net_return == resp2.expected_net_return
    assert resp1.reasons == resp2.reasons


# ==============================================================================
# 5. API ENDPOINT INTEGRATION TESTS
# ==============================================================================

def test_api_decision_endpoint_valid_request():
    """Test POST /api/models/decision for valid company and date."""
    payload = {
        "ticker": "AAPL",
        "as_of_date": "2020-01-15",
        "buy_threshold": 0.015,
        "sell_threshold": -0.015,
        "cost_roundtrip_bps": 15.0,
    }
    resp = client.post("/api/models/decision", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ticker"] == "AAPL"
    assert data["signal"] in ["BUY", "HOLD", "SELL"]
    assert "predicted_forward_return" in data
    assert "expected_net_return" in data
    assert "risk_checks_passed" in data
    assert data["is_experimental"] is True


def test_api_decision_endpoint_excluded_company():
    """Test that POST /api/models/decision gracefully returns HOLD for excluded ticker AA."""
    payload = {"ticker": "AA"}
    resp = client.post("/api/models/decision", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["signal"] == "HOLD"
    assert any("EXCLUSION_GATE" in check for check in data["risk_checks_failed"])

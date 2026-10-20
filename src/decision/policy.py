"""
Threshold-Based Decision Policy (Phase 5G).

Transforms model return forecasts into cautious, explainable BUY / HOLD / SELL candidate signals
by applying risk gating, transaction cost deductions, and calibrated thresholds.
"""

from typing import Optional, List, Dict, Any
from src.decision.schema import (
    SignalType,
    DecisionContractRequest,
    DecisionContractResponse,
)
from src.decision.cost import TransactionCostModel
from src.decision.uncertainty import ResidualUncertaintyEstimator
from src.decision.risk import RiskGateEvaluator


class ThresholdDecisionPolicy:
    """
    Executes threshold-based decision logic under strict risk and uncertainty controls.
    """

    def __init__(self, uncertainty_estimator: Optional[ResidualUncertaintyEstimator] = None):
        self.uncertainty_estimator = uncertainty_estimator

    def evaluate(self, request: DecisionContractRequest) -> DecisionContractResponse:
        """
        Evaluates a single decision request and produces a typed decision contract response.
        """
        cost_model = TransactionCostModel()
        roundtrip_cost = cost_model.calculate_roundtrip_cost(request.cost_config)
        cfg = request.risk_config

        # 1. Determine quantitative uncertainty
        uncertainty_val: Optional[float] = request.forecast_uncertainty
        uncertainty_method = "request_provided"
        if uncertainty_val is None and self.uncertainty_estimator is not None:
            uncertainty_val = self.uncertainty_estimator.get_uncertainty()
            uncertainty_method = self.uncertainty_estimator.method_name
        elif uncertainty_val is None:
            uncertainty_method = "unavailable"

        # 2. Evaluate all active risk gates
        all_passed, passed_checks, failed_checks, warnings = RiskGateEvaluator.evaluate_gates(
            request=request,
            uncertainty=uncertainty_val,
        )

        reasons: List[str] = []
        signal = SignalType.HOLD
        expected_net_return = request.predicted_forward_return
        threshold_applied = 0.0

        # 3. Determine signal based on risk checks and threshold conditions
        if not all_passed:
            # Gating failure forces HOLD regardless of forecast magnitude
            signal = SignalType.HOLD
            threshold_applied = 0.0
            reasons.append("SIGNAL FORCED TO HOLD: One or more defensive risk gates failed.")
            for fail_msg in failed_checks:
                reasons.append(f"FAILED CHECK: {fail_msg}")
        else:
            # All risk gates passed -> evaluate directional thresholds against net expected returns
            pred = request.predicted_forward_return
            if pred > 0:
                net_buy = cost_model.calculate_expected_net_return(pred, SignalType.BUY, request.cost_config)
                expected_net_return = net_buy
                threshold_applied = cfg.buy_threshold
                if net_buy >= cfg.buy_threshold:
                    signal = SignalType.BUY
                    reasons.append(
                        f"BUY CANDIDATE SIGNAL: Net expected return ({net_buy:.4%}) clears BUY threshold ({cfg.buy_threshold:.4%}) after {roundtrip_cost*10000:.1f} bps round-trip friction."
                    )
                else:
                    signal = SignalType.HOLD
                    reasons.append(
                        f"HOLD: Positive forecast ({pred:.4%}) yields net return ({net_buy:.4%}) that fails to clear BUY threshold ({cfg.buy_threshold:.4%})."
                    )
            elif pred < 0:
                net_sell = cost_model.calculate_expected_net_return(pred, SignalType.SELL, request.cost_config)
                expected_net_return = net_sell
                threshold_applied = cfg.sell_threshold
                if net_sell <= cfg.sell_threshold:
                    signal = SignalType.SELL
                    reasons.append(
                        f"SELL CANDIDATE SIGNAL: Net downward expected return ({net_sell:.4%}) clears SELL threshold ({cfg.sell_threshold:.4%}) after factoring in {roundtrip_cost*10000:.1f} bps friction."
                    )
                else:
                    signal = SignalType.HOLD
                    reasons.append(
                        f"HOLD: Negative forecast ({pred:.4%}) yields net return ({net_sell:.4%}) that does not clear SELL threshold ({cfg.sell_threshold:.4%})."
                    )
            else:
                signal = SignalType.HOLD
                threshold_applied = 0.0
                reasons.append("HOLD: Forecast return is exactly 0.0 (neutral baseline).")

        # 4. Construct comprehensive provenance metadata
        provenance: Dict[str, Any] = {
            "model_id": request.model_id,
            "model_version": request.model_version,
            "training_cutoff_date": request.training_cutoff_date,
            "horizon": request.target_horizon,
            "cost_breakdown": cost_model.calculate_cost_breakdown(request.cost_config),
            "uncertainty_metadata": {
                "uncertainty_value": uncertainty_val,
                "method": uncertainty_method,
            },
        }

        return DecisionContractResponse(
            signal=signal,
            ticker=request.ticker.upper(),
            company_id=request.company_id,
            decision_timestamp=request.decision_timestamp,
            predicted_forward_return=round(request.predicted_forward_return, 6),
            expected_net_return=round(expected_net_return, 6),
            total_cost_deducted=round(roundtrip_cost, 6),
            cost_assumptions_bps=request.cost_config.total_roundtrip_bps,
            estimated_uncertainty=round(uncertainty_val, 6) if uncertainty_val is not None else None,
            uncertainty_method=uncertainty_method,
            threshold_applied=threshold_applied,
            risk_checks_passed=passed_checks,
            risk_checks_failed=failed_checks,
            reasons=reasons,
            data_quality_warnings=warnings,
            model_provenance=provenance,
            is_experimental=True,
        )

"""
Risk Gate Controls and Evaluation (Phase 5G).

Implements explicit, configurable risk gates that protect against:
- Excessive forecast uncertainty
- Inadequate net return clearing transaction costs
- Stale or missing market data
- Incomplete feature inputs
- Extreme market volatility regimes
- Inverted temporal model provenance
"""

from typing import Tuple, List, Optional
from datetime import datetime, timezone
import pandas as pd

from src.decision.schema import DecisionContractRequest, RiskGateConfig
from src.decision.cost import TransactionCostModel


class RiskGateEvaluator:
    """
    Evaluates configurable risk gates for decision requests.
    Returns (all_passed, passed_checks, failed_checks, warnings).
    """

    EXCLUDED_TICKERS = {
        "AA": "Corporate split identity ambiguity between Arconic Inc. and Alcoa Corp."
    }

    @classmethod
    def evaluate_gates(
        cls,
        request: DecisionContractRequest,
        uncertainty: Optional[float] = None,
    ) -> Tuple[bool, List[str], List[str], List[str]]:
        """
        Executes all active risk checks.
        :returns:
            all_passed (bool): True only if every mandatory gate passes.
            passed_checks (List[str]): Descriptions of satisfied gates.
            failed_checks (List[str]): Descriptions of breached gates.
            warnings (List[str]): Operational and data caveats.
        """
        passed: List[str] = []
        failed: List[str] = []
        warnings: List[str] = []
        cfg = request.risk_config

        # 1. Company Identity & Exclusion Gate
        if request.ticker.upper() in cls.EXCLUDED_TICKERS:
            failed.append(f"EXCLUSION_GATE: Ticker '{request.ticker}' is excluded: {cls.EXCLUDED_TICKERS[request.ticker.upper()]}")
        else:
            passed.append(f"COMPANY_IDENTITY_GATE: Ticker '{request.ticker}' is eligible.")

        # 2. Model Provenance & Temporal Cutoff Gate
        if request.training_cutoff_date:
            try:
                dec_dt = pd.to_datetime(request.decision_timestamp, utc=True)
                cutoff_dt = pd.to_datetime(request.training_cutoff_date, utc=True)
                if dec_dt.date() < cutoff_dt.date():
                    failed.append(
                        f"PROVENANCE_GATE: Decision date ({dec_dt.date()}) precedes model training cutoff ({cutoff_dt.date()}). Inverted temporal deployment."
                    )
                else:
                    passed.append(f"PROVENANCE_GATE: Decision date follows training cutoff ({cutoff_dt.date()}).")
            except Exception as e:
                warnings.append(f"Could not parse temporal provenance: {e}")
        else:
            warnings.append("No training cutoff date provided in request metadata.")

        # 3. Forecast Uncertainty Gate
        if cfg.enforce_uncertainty_gate:
            if uncertainty is None or not (uncertainty > 0):
                failed.append("UNCERTAINTY_GATE: Valid forecast uncertainty estimate is unavailable.")
            elif uncertainty > cfg.max_uncertainty:
                failed.append(
                    f"UNCERTAINTY_GATE: Forecast uncertainty ({uncertainty:.4f}) exceeds threshold ({cfg.max_uncertainty:.4f})."
                )
            else:
                passed.append(f"UNCERTAINTY_GATE: Forecast uncertainty ({uncertainty:.4f}) within ceiling ({cfg.max_uncertainty:.4f}).")
        else:
            warnings.append("Forecast uncertainty gate is disabled in configuration.")

        # 4. Feature Completeness Gate
        meta = request.feature_metadata or {}
        n_features_used = meta.get("n_features_used")
        n_features_required = meta.get("n_features_required", 17)
        if n_features_used is not None and n_features_required > 0:
            ratio = n_features_used / float(n_features_required)
            if ratio < cfg.min_features_required_ratio:
                failed.append(
                    f"FEATURE_COMPLETENESS_GATE: Only {n_features_used}/{n_features_required} ({ratio:.1%}) features present, below required {cfg.min_features_required_ratio:.1%}."
                )
            else:
                passed.append(f"FEATURE_COMPLETENESS_GATE: Feature availability ({ratio:.1%}) meets requirement.")
        else:
            warnings.append("Feature completeness ratio could not be verified from request metadata.")

        # 5. Data Freshness Gate
        as_of_str = meta.get("as_of_date")
        if as_of_str:
            try:
                dec_date = pd.to_datetime(request.decision_timestamp, utc=True).date()
                as_of_date = pd.to_datetime(as_of_str).date()
                age_days = (dec_date - as_of_date).days
                if age_days > cfg.max_staleness_days:
                    failed.append(f"STALENESS_GATE: Underlying data is {age_days} days old, exceeding limit of {cfg.max_staleness_days} days.")
                else:
                    passed.append(f"STALENESS_GATE: Data freshness ({age_days} days old) is acceptable.")
            except Exception as e:
                warnings.append(f"Data freshness could not be parsed: {e}")

        # 6. Abnormal Volatility Gate
        vol = request.rolling_volatility_5d
        if vol is not None:
            if vol > cfg.max_rolling_volatility_5d:
                failed.append(
                    f"VOLATILITY_GATE: Rolling 5-session volatility ({vol:.4f}) exceeds safe ceiling ({cfg.max_rolling_volatility_5d:.4f})."
                )
            else:
                passed.append(f"VOLATILITY_GATE: Volatility ({vol:.4f}) is within acceptable boundary.")

        # 7. Cost Hurdle Gate (Pre-check)
        cost_model = TransactionCostModel()
        roundtrip_cost = cost_model.calculate_roundtrip_cost(request.cost_config)
        abs_pred = abs(request.predicted_forward_return)
        min_required = roundtrip_cost + cfg.min_net_return_hurdle
        if abs_pred < min_required:
            failed.append(
                f"COST_HURDLE_GATE: Gross return ({abs_pred:.4f}) does not clear costs ({roundtrip_cost:.4f}) + net hurdle ({cfg.min_net_return_hurdle:.4f}) = {min_required:.4f}."
            )
        else:
            passed.append(f"COST_HURDLE_GATE: Gross return ({abs_pred:.4f}) clears minimum cost hurdle ({min_required:.4f}).")

        all_passed = (len(failed) == 0)
        return all_passed, passed, failed, warnings

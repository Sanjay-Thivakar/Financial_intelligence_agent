"""
Decision & Risk Layer Schema and Data Contracts (Phase 5G).

Defines typed interfaces, configurable cost assumptions, risk gate parameters,
and standard response models for experimental BUY / HOLD / SELL candidate signals.
"""

from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class SignalType(str, Enum):
    """Experimental signal action recommendation."""
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"


class TransactionCostConfig(BaseModel):
    """
    Configurable transaction cost and slippage parameters in basis points (bps).
    1 bps = 0.0001 (0.01%).
    """
    entry_fee_bps: float = Field(2.5, ge=0.0, description="Brokerage entry fee in bps")
    exit_fee_bps: float = Field(2.5, ge=0.0, description="Brokerage exit fee in bps")
    half_spread_bps: float = Field(2.5, ge=0.0, description="Half bid-ask spread in bps")
    slippage_bps: float = Field(2.5, ge=0.0, description="One-way execution slippage in bps (2.5 bps entry + 2.5 bps exit = 5 bps total)")

    @property
    def total_roundtrip_bps(self) -> float:
        """Total round-trip friction = entry + exit + 2 * half_spread + 2 * slippage."""
        return self.entry_fee_bps + self.exit_fee_bps + (2 * self.half_spread_bps) + (2 * self.slippage_bps)

    @property
    def total_roundtrip_decimal(self) -> float:
        """Total round-trip cost as a decimal fraction."""
        return self.total_roundtrip_bps / 10000.0


class RiskGateConfig(BaseModel):
    """
    Configurable risk control thresholds and policy gates.
    """
    buy_threshold: float = Field(0.015, description="Minimum net expected return required for BUY (e.g. 1.5%)")
    sell_threshold: float = Field(-0.015, description="Maximum net expected return threshold for SELL (e.g. -1.5%)")
    max_uncertainty: float = Field(0.08, gt=0.0, description="Maximum acceptable forecast residual standard error (e.g. 8.0%)")
    min_net_return_hurdle: float = Field(0.005, description="Minimum net expected return hurdle after costs (e.g. 0.5%)")
    max_staleness_days: int = Field(5, ge=1, description="Maximum calendar days of market data staleness allowed")
    min_features_required_ratio: float = Field(0.80, ge=0.1, le=1.0, description="Minimum fraction of required features present")
    max_rolling_volatility_5d: float = Field(0.15, gt=0.0, description="Maximum rolling 5-session volatility ceiling")
    enforce_uncertainty_gate: bool = Field(True, description="Whether to require valid uncertainty below threshold")


class DecisionContractRequest(BaseModel):
    """
    Strictly validated input contract for the Decision & Risk Layer.
    """
    company_id: str = Field(..., description="Canonical entity ID (e.g. US_CIK_0000320193)")
    ticker: str = Field(..., description="Asset ticker symbol (e.g. AAPL)")
    decision_timestamp: str = Field(..., description="ISO 8601 UTC timestamp of decision cutoff")
    target_horizon: str = Field(
        default="5-trading-session (T+1 open to T+5 close)",
        description="Standardized target forecast horizon"
    )
    predicted_forward_return: float = Field(..., description="Model forecast return")
    forecast_uncertainty: Optional[float] = Field(None, ge=0.0, description="Residual standard error or uncertainty proxy")
    rolling_volatility_5d: Optional[float] = Field(None, ge=0.0, description="Rolling 5-session volatility")
    feature_metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata on features present and missing")
    model_id: str = Field(..., description="Identifier of the model generating the forecast")
    model_version: str = Field(default="1.0.0", description="Model version string")
    training_cutoff_date: Optional[str] = Field(None, description="Historical date through which model was trained (YYYY-MM-DD)")
    cost_config: TransactionCostConfig = Field(default_factory=TransactionCostConfig)
    risk_config: RiskGateConfig = Field(default_factory=RiskGateConfig)


class DecisionContractResponse(BaseModel):
    """
    Strictly validated output contract for the Decision & Risk Layer.
    """
    signal: SignalType = Field(..., description="Candidate experimental signal (BUY, HOLD, SELL)")
    ticker: str
    company_id: str
    decision_timestamp: str
    predicted_forward_return: float
    expected_net_return: float
    total_cost_deducted: float
    cost_assumptions_bps: float
    estimated_uncertainty: Optional[float]
    uncertainty_method: str
    threshold_applied: float
    risk_checks_passed: List[str] = Field(default_factory=list)
    risk_checks_failed: List[str] = Field(default_factory=list)
    reasons: List[str] = Field(default_factory=list)
    data_quality_warnings: List[str] = Field(default_factory=list)
    model_provenance: Dict[str, Any] = Field(default_factory=dict)
    is_experimental: bool = True

"""
Typed Pydantic Schemas for Financial Intelligence Agent Dashboard API.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class CompanyMetadata(BaseModel):
    ticker: str
    company_id: str
    company_name: str
    cik: str
    sector: str
    membership_interval: str
    min_date: str
    max_date: str
    total_sessions: int
    sec_coverage_status: str
    news_coverage_status: str
    pilot_eligible: bool
    notes: Optional[str] = None


class MarketSeriesPoint(BaseModel):
    trading_date: str
    open: float
    high: float
    low: float
    close: float
    adjusted_close: float
    volume: float
    market_return_1d: Optional[float] = None
    market_return_5d: Optional[float] = None
    market_volatility_21d: Optional[float] = None
    market_sma_20d: Optional[float] = None
    market_sma_50d: Optional[float] = None
    market_rsi_14d: Optional[float] = None
    target_forward_return_5d: Optional[float] = None
    target_forward_return_5d_valid: Optional[bool] = None


class CompanyMarketResponse(BaseModel):
    ticker: str
    company_id: str
    company_name: str
    data_source: str
    adjustment_semantics: str
    total_points: int
    latest_observation_date: str
    latest_adjusted_close: float
    series: List[MarketSeriesPoint]


class FoldMetricResult(BaseModel):
    fold: int
    train_start: str
    train_end: str
    train_rows: int
    val_start: str
    val_end: str
    val_rows: int
    regime_notes: str
    zero_rmse: float
    zero_mae: float
    zero_hit: float
    median_rmse: float
    median_mae: float
    median_hit: float
    market_ridge_rmse: float
    market_ridge_mae: float
    market_ridge_hit: float
    market_ridge_ic: float
    market_ridge_alpha: float
    fund_ridge_rmse: Optional[float] = None
    fund_ridge_mae: Optional[float] = None
    fund_ridge_hit: Optional[float] = None
    fund_ridge_ic: Optional[float] = None
    fund_ridge_alpha: Optional[float] = None
    best_model_mae: str


class ModelEvaluationSummaryResponse(BaseModel):
    experiment_name: str
    provenance: str
    verified_cohort: List[str]
    target_definition: str
    purge_sessions: int
    overall_winner_mae: str
    critical_findings: List[str]
    fold_results: List[FoldMetricResult]
    two_company_cohort_results: List[FoldMetricResult]


class PredictionRequest(BaseModel):
    ticker: str
    as_of_date: Optional[str] = None


class PredictionResponse(BaseModel):
    status: str  # "available", "unavailable", "error"
    ticker: str
    company_id: Optional[str] = None
    as_of_timestamp: Optional[str] = None
    target_horizon: str
    predicted_forward_return: Optional[float] = None
    predicted_forward_return_pct: Optional[str] = None
    model_id: Optional[str] = None
    features_used: List[str] = Field(default_factory=list)
    message: str
    limitations: List[str] = Field(default_factory=list)
    is_experimental: bool = True


class DecisionRequest(BaseModel):
    """Request model for experimental BUY / HOLD / SELL decision evaluation."""
    ticker: str
    as_of_date: Optional[str] = None
    buy_threshold: Optional[float] = Field(None, description="Override for buy threshold (e.g. 0.015 for 1.5%)")
    sell_threshold: Optional[float] = Field(None, description="Override for sell threshold (e.g. -0.015 for -1.5%)")
    max_uncertainty: Optional[float] = Field(None, description="Override for max uncertainty ceiling")
    cost_roundtrip_bps: Optional[float] = Field(None, description="Override for total roundtrip costs in bps")


# =====================================================================
# Phase 5L — 60-Company Screener, Research Signals & Diagnostics Schemas
# =====================================================================

class ScreenerCompanyItem(BaseModel):
    """Summarized company item for the 60-company research screener."""
    ticker: str
    company_name: str
    company_id: str
    cik: str
    sector: str
    coverage_status: str  # "ELIGIBLE", "ELIGIBLE_WITH_LIMITATIONS", "EXCLUDED"
    completeness_pct: float
    total_sessions: int
    earliest_date: str
    latest_date: str
    is_truncated: bool
    limitations_note: Optional[str] = None
    observation_date: Optional[str] = None
    predicted_return: Optional[float] = None
    predicted_return_pct: Optional[str] = None
    expected_net_return: Optional[float] = None
    expected_net_return_pct: Optional[str] = None
    forecast_uncertainty: Optional[float] = None
    forecast_uncertainty_pct: Optional[str] = None
    signal: str  # "BUY", "HOLD", "SELL", "UNAVAILABLE", "EXCLUDED"
    risk_status: str
    model_id: Optional[str] = None
    prediction_timestamp: Optional[str] = None
    failed_gate_count: int = 0
    reasons: List[str] = Field(default_factory=list)


class ScreenerResponse(BaseModel):
    """Response payload for 60-company screener."""
    status: str = "success"
    mode: str = "HISTORICAL_RESEARCH"
    disclaimer: str
    total_cohort_count: int = 60
    filtered_count: int
    default_model: str = "ridge_regression"
    active_model: str
    as_of_date: Optional[str] = None
    available_models: List[str] = Field(default_factory=list)
    available_sectors: List[str] = Field(default_factory=list)
    signal_summary: Dict[str, int] = Field(default_factory=dict)
    companies: List[ScreenerCompanyItem]
    excluded_companies: List[Dict[str, str]] = Field(default_factory=list)


class DecisionFunnelStage(BaseModel):
    """A single stage in the 8-stage decision funnel."""
    stage_number: int
    stage_name: str
    status: str  # "PASS", "FAIL", "NOT EVALUATED"
    metric_value: Optional[str] = None
    threshold_applied: Optional[str] = None
    explanation: str


class CompanyResearchDetailResponse(BaseModel):
    """Comprehensive company research detail response with historical series and 8-stage decision funnel."""
    status: str
    ticker: str
    company_name: str
    company_id: str
    cik: str
    sector: str
    coverage_status: str
    is_truncated: bool
    limitations_note: Optional[str] = None
    market_notes: Optional[str] = None
    sec_notes: Optional[str] = None
    observation_date: Optional[str] = None
    data_freshness_days: Optional[int] = None
    model_id: Optional[str] = None
    fold: Optional[int] = None
    forecast_horizon: str = "5 Trading Days (T close -> T+1 open -> T+5 close)"
    predicted_return: Optional[float] = None
    predicted_return_pct: Optional[str] = None
    expected_net_return: Optional[float] = None
    expected_net_return_pct: Optional[str] = None
    forecast_uncertainty: Optional[float] = None
    forecast_uncertainty_pct: Optional[str] = None
    uncertainty_method: Optional[str] = None
    signal: str
    decision_category: str  # "BUY_SIGNAL", "HOLD_INSUFFICIENT_RETURN", "HOLD_RISK_GATED", "UNAVAILABLE_MISSING_DATA", "EXCLUDED"
    roundtrip_cost_bps: float = 15.0
    cost_breakdown: Dict[str, float] = Field(default_factory=dict)
    decision_reasons: List[str] = Field(default_factory=list)
    funnel_stages: List[DecisionFunnelStage] = Field(default_factory=list)
    risk_checks_passed: List[str] = Field(default_factory=list)
    risk_checks_failed: List[str] = Field(default_factory=list)
    data_quality_warnings: List[str] = Field(default_factory=list)
    historical_price_series: List[Dict[str, Any]] = Field(default_factory=list)
    available_prediction_dates: List[str] = Field(default_factory=list)
    disclaimer: str = (
        "Historical research mode — predictions and signals are based on archived data (2019–2020), "
        "not current market conditions. No real orders are executed and no signals constitute investment advice."
    )


class SignalDetailResponse(BaseModel):
    """Detailed signal contract response for a company with decision funnel."""
    status: str
    ticker: str
    company_id: str
    decision_timestamp: str
    observation_date: str
    model_id: str
    predicted_forward_return: Optional[float] = None
    expected_net_return: Optional[float] = None
    signal: str
    decision_category: str
    roundtrip_cost_bps: float
    threshold_applied: float
    funnel_stages: List[DecisionFunnelStage] = Field(default_factory=list)
    risk_checks_passed: List[str] = Field(default_factory=list)
    risk_checks_failed: List[str] = Field(default_factory=list)
    reasons: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    is_experimental: bool = True


class BulkSignalsResponse(BaseModel):
    """Bulk signals overview across the 60-company cohort."""
    status: str = "success"
    mode: str = "HISTORICAL_RESEARCH"
    model_id: str
    as_of_date: Optional[str] = None
    total_signals: int
    signal_summary: Dict[str, int] = Field(default_factory=dict)
    signals: List[Dict[str, Any]] = Field(default_factory=list)


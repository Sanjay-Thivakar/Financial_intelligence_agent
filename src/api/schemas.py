"""
Typed Pydantic Schemas for Financial Intelligence Agent Dashboard API.
"""

from enum import Enum
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


# =====================================================================
# Phase 6.2 — Canonical Company Universe & Capability Contract (v1)
# =====================================================================

class CapabilityStatus(str, Enum):
    """Semantic status of a specific modality or feature capability."""
    SUPPORTED = "SUPPORTED"
    NOT_DOWNLOADED_IN_PILOT = "NOT_DOWNLOADED_IN_PILOT"
    EXCLUDED_BY_POLICY = "EXCLUDED_BY_POLICY"
    UNAVAILABLE = "UNAVAILABLE"
    UNVERIFIED = "UNVERIFIED"


class MarketCoverageStatus(str, Enum):
    """Descriptive data completeness classification for historical market series."""
    COMPLETE = "COMPLETE"
    NEAR_COMPLETE = "NEAR_COMPLETE"
    TRUNCATED = "TRUNCATED"
    EXCLUDED = "EXCLUDED"
    UNVERIFIED = "UNVERIFIED"


class IdentityStatus(str, Enum):
    """Entity identity resolution and universe classification."""
    CANONICAL_CONSTITUENT = "CANONICAL_CONSTITUENT"
    EXCLUDED_AMBIGUOUS_IDENTITY = "EXCLUDED_AMBIGUOUS_IDENTITY"
    ALIAS_SHARE_CLASS = "ALIAS_SHARE_CLASS"


class CompanyIdentity(BaseModel):
    """Stable entity identifier, corporate CIK, and canonical ticker representation."""
    company_id: str
    canonical_ticker: str
    ticker_aliases: List[str] = Field(default_factory=list)
    related_share_classes: List[str] = Field(default_factory=list)
    share_class_description: Optional[str] = None
    company_name: str
    cik: Optional[str] = None
    sector: Optional[str] = None
    universe_membership: str = "HISTORICAL_RESEARCH_COHORT"
    identity_status: IdentityStatus = IdentityStatus.CANONICAL_CONSTITUENT
    identity_notes: Optional[str] = None


class MarketArtifactCoverage(BaseModel):
    """Raw physical market series bounds from physical parquet store."""
    status: CapabilityStatus = CapabilityStatus.SUPPORTED
    earliest_date: Optional[str] = None
    latest_date: Optional[str] = None
    total_sessions: Optional[int] = None
    source_artifact: str = "data/processed/market/phase5i_market_expansion.parquet"
    feature_data_available: bool = True
    feature_schema_compatibility: str = "17_technical_indicators_v1"
    limitations_note: Optional[str] = None


class EvaluationWindowCoverage(BaseModel):
    """Phase 5J walk-forward evaluation window metrics and completeness (2019-01-02 to 2020-06-03)."""
    window_start_date: str = "2019-01-02"
    window_end_date: str = "2020-06-03"
    expected_window_sessions: int = 363
    observed_window_sessions: int
    completeness_pct: float
    completeness_denominator: int = 363
    is_truncated: bool = False
    descriptive_category: MarketCoverageStatus
    source_manifest: str = "data/processed/universe/phase5j_company_eligibility.csv"
    limitations_note: Optional[str] = None


class MultiModalCoverage(BaseModel):
    """Multi-modal dataset availability (SEC facts, 8-K events, News)."""
    sec_fundamentals_status: CapabilityStatus
    sec_fundamentals_notes: Optional[str] = None
    sec_events_status: CapabilityStatus
    sec_events_notes: Optional[str] = None
    news_status: CapabilityStatus = CapabilityStatus.EXCLUDED_BY_POLICY
    news_notes: Optional[str] = None


class EvaluationTrackEligibility(BaseModel):
    """Walk-forward evaluation track and fold eligibility from Phase 5J."""
    track_a_market_only: bool = True
    track_b_market_plus_fund: bool = False
    track_c_market_plus_events: bool = False
    track_d_combined: bool = False
    eligible_folds: List[int] = Field(default_factory=list)
    fold_limitations: Optional[str] = None
    source_manifest: str = "data/processed/universe/phase5j_company_eligibility.csv"


class HistoricalPredictionCoverage(BaseModel):
    """Archived out-of-sample forward-return prediction metadata from Phase 5K."""
    archived_predictions_available: bool = True
    available_models: List[str] = Field(default_factory=list)
    available_folds: List[int] = Field(default_factory=list)
    earliest_prediction_date: Optional[str] = None
    latest_prediction_date: Optional[str] = None
    source_artifact: str = "data/processed/research/phase5k/phase5k_predictions_oos.parquet"


class RuntimeExecutionCapabilities(BaseModel):
    """Runtime model inference, decision gating, and portfolio simulation capabilities."""
    runtime_inference_supported: bool = False
    runtime_inference_model: Optional[str] = None
    runtime_decision_supported: bool = False
    historical_decision_supported: bool = True
    portfolio_simulation_status: CapabilityStatus = CapabilityStatus.UNVERIFIED
    portfolio_simulation_notes: Optional[str] = (
        "Offline batch multi-asset simulation engine only. Interactive per-company simulation "
        "is unverified; runtime execution is unsupported."
    )
    interactive_trade_execution: bool = False


class CompanyCapabilityItem(BaseModel):
    """Comprehensive company capability contract representing all verified dimensions."""
    identity: CompanyIdentity
    market_artifact: MarketArtifactCoverage
    evaluation_window: EvaluationWindowCoverage
    multi_modal: MultiModalCoverage
    evaluation_tracks: EvaluationTrackEligibility
    predictions: HistoricalPredictionCoverage
    runtime: RuntimeExecutionCapabilities
    provenance_sources: List[str] = Field(default_factory=list)
    data_limitations: List[str] = Field(default_factory=list)


class CompanyCapabilityListResponse(BaseModel):
    """Versioned capability contract response for the validated 60-company cohort."""
    status: str = "success"
    version: str = "v1"
    total_cohort_count: int
    as_of_reference: str = "2020-06-03"
    companies: List[CompanyCapabilityItem] = Field(default_factory=list)
    excluded_entities: List[Dict[str, Any]] = Field(default_factory=list)


# =====================================================================
# Phase 6.5 — Company Archived Prediction Series Schemas
# =====================================================================

class ArchivedPredictionRecord(BaseModel):
    """Single out-of-sample prediction record from Phase 5K historical research archive."""
    trading_date: str
    fold: int
    model_id: str
    predicted_return: float
    target_return: float
    residual: float
    sigma_train: float
    adjusted_close: float


class CompanyArchivedPredictionsResponse(BaseModel):
    """Archived out-of-sample forward-return prediction series for a validated company."""
    status: str = "available"  # "available", "empty", "unavailable"
    ticker: str
    company_name: str
    company_id: str
    sector: str
    total_records: int
    returned_records: int
    available_models: List[str] = Field(default_factory=list)
    available_folds: List[int] = Field(default_factory=list)
    earliest_date: Optional[str] = None
    latest_date: Optional[str] = None
    is_truncated: bool = False
    source_artifact: str = "data/processed/research/phase5k/phase5k_predictions_oos.parquet"
    target_definition: str = "5-session forward return: decision at session T close, entry at session T+1 open, exit at session T+5 close"
    disclaimer: str = (
        "Historical out-of-sample research archive (2019-2020). Predictions were computed strictly "
        "using walk-forward trained models on training splits with 5-session purge gaps. "
        "Realized forward returns reflect actual historical price action (T+1 open to T+5 close) "
        "and are NOT model predictions. Not investment advice or live runtime inference."
    )
    predictions: List[ArchivedPredictionRecord] = Field(default_factory=list)




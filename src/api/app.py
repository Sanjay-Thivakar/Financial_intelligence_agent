"""
FastAPI Application for Financial Intelligence Agent Prototype Dashboard.

Exposes typed endpoints for company metadata, market series with technical overlays,
model evaluation summaries (with Phase 5D provenance), model runtime status,
and experimental forward-return predictions.
"""

from pathlib import Path
from typing import List, Optional
import logging
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from src.api.schemas import (
    CompanyMetadata,
    CompanyMarketResponse,
    ModelEvaluationSummaryResponse,
    PredictionRequest,
    PredictionResponse,
    DecisionRequest,
    ScreenerResponse,
    CompanyResearchDetailResponse,
    SignalDetailResponse,
    BulkSignalsResponse,
    CompanyCapabilityItem,
    CompanyCapabilityListResponse,
    CompanyArchivedPredictionsResponse,
)
from src.decision.schema import DecisionContractResponse
from src.api.service import dashboard_service, EXCLUDED_COMPANIES

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Financial Intelligence Agent API",
    description="Institutional prototype API for quantitative market analysis, SEC point-in-time facts, and experimental return forecasting.",
    version="1.0.0",
)

# CORS configuration for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health_check():
    """System health check and operational status."""
    return {
        "status": "operational",
        "system": "Financial Intelligence Agent Prototype API",
        "mode": "RESEARCH / EXPERIMENTAL",
        "version": "1.0.0",
    }


@app.get("/api/companies", response_model=List[CompanyMetadata])
def list_companies():
    """
    Returns list of eligible companies currently supported by the prototype.
    AA is strictly excluded due to corporate split identity ambiguity.
    """
    return dashboard_service.get_eligible_companies()


@app.get("/api/companies/{ticker}", response_model=CompanyMetadata)
def get_company(ticker: str):
    """
    Returns detailed metadata for a single eligible company.
    Rejects excluded or unknown companies.
    """
    ticker_clean = ticker.upper()
    if ticker_clean in EXCLUDED_COMPANIES:
        raise HTTPException(
            status_code=400,
            detail=f"Company {ticker_clean} is excluded: {EXCLUDED_COMPANIES[ticker_clean]}",
        )

    meta = dashboard_service.get_company_metadata(ticker_clean)
    if not meta:
        raise HTTPException(
            status_code=404,
            detail=f"Ticker '{ticker_clean}' not found in eligible prototype universe.",
        )
    return meta


@app.get("/api/companies/{ticker}/market", response_model=CompanyMarketResponse)
def get_company_market(
    ticker: str,
    limit: int = Query(500, ge=10, le=2500, description="Maximum number of historical points to return"),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
):
    """
    Returns historical market quotes (OHLCV, Adjusted Close) and computed technical indicators
    (SMA, RSI, Volatility, Returns, Forward Target) for the requested company.
    Supports both the four-company prototype catalog and the expanded 60-company research cohort.
    """
    ticker_clean = ticker.strip().upper()
    if ticker_clean in EXCLUDED_COMPANIES:
        raise HTTPException(
            status_code=400,
            detail=f"Company {ticker_clean} is excluded: {EXCLUDED_COMPANIES[ticker_clean]}",
        )
    if ticker_clean == "GOOGL":
        raise HTTPException(
            status_code=404,
            detail=(
                "Ticker 'GOOGL' is a distinct share class (Class A voting) of Alphabet Inc. "
                "(CIK 0001652044) and is not a separately supported market ticker in this research cohort "
                "(which tracks GOOG Class C). Market data is not interchangeable."
            ),
        )

    try:
        response = dashboard_service.get_company_market(
            ticker=ticker_clean,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"Market data artifact for ticker '{ticker_clean}' is not available: {e}")

    if not response:
        raise HTTPException(
            status_code=404,
            detail=f"Market data for ticker '{ticker_clean}' is not available.",
        )
    return response


@app.get("/api/models/evaluation", response_model=ModelEvaluationSummaryResponse)
def get_evaluation_summary():
    """
    Returns structured walk-forward evaluation metrics and fold results from Phase 5D.
    Provenance is explicitly documented as report-derived from historical evaluation.
    """
    return dashboard_service.get_model_evaluation_summary()


@app.get("/api/models/status")
def get_model_status():
    """
    Returns current training and runtime status for baselines and predictive models.
    """
    return dashboard_service.get_model_status()


@app.post("/api/models/predict", response_model=PredictionResponse)
def predict_forward_return(request: PredictionRequest):
    """
    Experimental forward return prediction.
    Uses strict walk-forward trained Ridge regression on market features.
    Returns honest 'unavailable' response if inputs are missing or company is unsupported.
    Never fabricates predictions or BUY/HOLD/SELL signals.
    """
    return dashboard_service.predict_experimental(
        ticker=request.ticker,
        as_of_date=request.as_of_date,
    )


@app.post("/api/models/decision", response_model=DecisionContractResponse)
def evaluate_decision_signal(request: DecisionRequest):
    """
    Experimental BUY / HOLD / SELL candidate signal generation.
    Applies calibrated decision thresholds, transaction cost deductions,
    forecast uncertainty gates, and defensive risk controls.
    """
    return dashboard_service.get_decision(
        ticker=request.ticker,
        as_of_date=request.as_of_date,
        buy_threshold=request.buy_threshold,
        sell_threshold=request.sell_threshold,
        max_uncertainty=request.max_uncertainty,
        cost_roundtrip_bps=request.cost_roundtrip_bps,
    )


@app.get("/api/models/portfolio/research")
def get_portfolio_research_summary():
    """
    Returns Phase 5H portfolio simulation and rolling threshold evaluation artifacts.
    Covers Cash, Equal-Weight Buy & Hold, Fixed Policy (1.5%), and Rolling Threshold strategies.
    """
    return dashboard_service.get_portfolio_research_summary()


@app.get("/api/models/research/phase5j")
def get_phase5j_cross_sectional_research():
    """
    Returns Phase 5J validated 60-company cross-sectional evaluation,
    multi-modal track comparison, and portfolio simulation results.
    """
    return dashboard_service.get_phase5j_cross_sectional_research()


@app.get("/api/models/research/phase5k")
def get_phase5k_model_improvement_research():
    """
    Returns Phase 5K systematic model improvement results, multi-candidate comparisons,
    cross-sectional / sector-neutral transformations, and institutional portfolio simulations.
    """
    return dashboard_service.get_phase5k_model_improvement_research()


# =====================================================================
# Phase 5L — 60-Company Screener, Research Signals & Risk Diagnostics
# =====================================================================

@app.get("/api/research/companies", response_model=ScreenerResponse)
def get_60_company_screener(
    model_id: str = Query("ridge_regression", description="Candidate model identifier"),
    as_of_date: Optional[str] = Query(None, description="Historical observation date (YYYY-MM-DD)"),
    sector: Optional[str] = Query(None, description="GICS Sector filter"),
    signal: Optional[str] = Query(None, description="Signal filter: BUY, HOLD, SELL, UNAVAILABLE"),
    coverage: Optional[str] = Query(None, description="Coverage filter: complete or truncated"),
    search: Optional[str] = Query(None, description="Search ticker or company name"),
    sort_by: Optional[str] = Query(None, description="Sort column (ticker, company_name, sector, coverage, predicted_return, signal)"),
    sort_dir: str = Query("asc", description="Sort direction (asc, desc)"),
    limit: Optional[int] = Query(None, description="Limit results"),
    offset: int = Query(0, description="Offset results"),
):
    """
    Returns the complete 60-company research screener payload with live decision contracts,
    risk gate statuses, and out-of-sample forward return forecasts.
    """
    return dashboard_service.get_60_company_screener(
        model_id=model_id,
        as_of_date=as_of_date,
        sector=sector,
        signal=signal,
        coverage=coverage,
        search=search,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )


@app.get("/api/research/companies/{ticker}", response_model=CompanyResearchDetailResponse)
def get_company_research_detail(
    ticker: str,
    model_id: str = Query("ridge_regression", description="Candidate model identifier"),
    as_of_date: Optional[str] = Query(None, description="Historical observation date (YYYY-MM-DD)"),
):
    """
    Returns comprehensive company research profile, historical price series for charting,
    and complete 8-stage decision funnel diagnostics.
    """
    try:
        return dashboard_service.get_company_research_detail(
            ticker=ticker,
            model_id=model_id,
            as_of_date=as_of_date,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error processing research detail: {e}")


@app.get("/api/research/companies/{ticker}/predictions", response_model=CompanyArchivedPredictionsResponse)
def get_company_archived_predictions(
    ticker: str,
    model_id: Optional[str] = Query(None, description="Candidate model identifier"),
    fold: Optional[int] = Query(None, description="Walk-forward fold identifier (0, 1, 2, 3)"),
    limit: int = Query(200, ge=1, le=1000, description="Maximum prediction records to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
):
    """
    Returns verified archived out-of-sample forward-return predictions for a company
    from the Phase 5K research archive (phase5k_predictions_oos.parquet).
    Preserves strict separation between historical predictions and live runtime inference.
    """
    ticker_clean = ticker.strip().upper()
    if ticker_clean in EXCLUDED_COMPANIES:
        raise HTTPException(
            status_code=400,
            detail=f"Company {ticker_clean} is excluded: {EXCLUDED_COMPANIES[ticker_clean]}",
        )
    if ticker_clean == "GOOGL":
        raise HTTPException(
            status_code=404,
            detail=(
                "Ticker 'GOOGL' is a distinct share class (Class A voting) of Alphabet Inc. "
                "(CIK 0001652044) and is not a separately supported market ticker in this research cohort "
                "(which tracks GOOG Class C). Market data is not interchangeable."
            ),
        )

    try:
        resp = dashboard_service.get_company_archived_predictions(
            ticker=ticker_clean,
            model_id=model_id,
            fold=fold,
            limit=limit,
            offset=offset,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error processing archived predictions: {e}")

    if not resp:
        raise HTTPException(
            status_code=404,
            detail=f"Ticker '{ticker_clean}' is not part of the validated 60-company research cohort.",
        )
    return resp


@app.get("/api/research/signals", response_model=BulkSignalsResponse)
def get_research_signals(
    model_id: str = Query("ridge_regression", description="Candidate model identifier"),
    as_of_date: Optional[str] = Query(None, description="Historical observation date (YYYY-MM-DD)"),
    sector: Optional[str] = Query(None, description="GICS Sector filter"),
    signal: Optional[str] = Query(None, description="Signal filter: BUY, HOLD, SELL"),
):
    """
    Returns bulk signals and summary counts across the 60-company cohort.
    """
    return dashboard_service.get_research_signals(
        model_id=model_id,
        as_of_date=as_of_date,
        sector=sector,
        signal=signal,
    )


@app.get("/api/research/signals/{ticker}", response_model=SignalDetailResponse)
def get_company_signal_detail(
    ticker: str,
    model_id: str = Query("ridge_regression", description="Candidate model identifier"),
    as_of_date: Optional[str] = Query(None, description="Historical observation date (YYYY-MM-DD)"),
):
    """
    Returns detailed decision contract and 8-stage risk gate diagnostics for a single company.
    """
    try:
        return dashboard_service.get_company_signal_detail(
            ticker=ticker,
            model_id=model_id,
            as_of_date=as_of_date,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error processing signal detail: {e}")


# =====================================================================
# Phase 6.2 — Canonical Company Universe & Capability Contract Endpoints
# =====================================================================

@app.get("/api/v1/companies/capabilities", response_model=CompanyCapabilityListResponse, tags=["Capabilities"])
def list_company_capabilities():
    """
    Returns the authoritative capability inventory for the validated 60-company research cohort.
    Exposes granular coverage states, multi-modal availability, evaluation track eligibility,
    archived prediction metadata, and runtime inference compatibility.
    """
    try:
        return dashboard_service.get_company_capabilities_list()
    except Exception as e:
        logger.error(f"Error serving company capabilities: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error loading capability inventory: {e}")


@app.get("/api/v1/companies/capabilities/{ticker}", response_model=CompanyCapabilityItem, tags=["Capabilities"])
def get_company_capability(ticker: str):
    """
    Returns the comprehensive capability record for a single company in the expanded research cohort.
    Rejects unknown, excluded, or unsupported share-class tickers (such as GOOGL) with HTTP 404.
    """
    ticker_clean = ticker.strip().upper()
    if ticker_clean == "GOOGL":
        raise HTTPException(
            status_code=404,
            detail=(
                "Ticker 'GOOGL' is a distinct share class (Class A voting) of Alphabet Inc. "
                "(CIK 0001652044) and is not a separately supported market ticker in this research cohort "
                "(which tracks GOOG Class C). Share classes are not interchangeable."
            ),
        )
    cap = dashboard_service.get_company_capability(ticker_clean)
    if not cap:
        ex_msg = EXCLUDED_COMPANIES.get(ticker_clean, "")
        detail = f"Ticker '{ticker_clean}' is not found in the validated research cohort."
        if ex_msg:
            detail += f" {ex_msg}"
        raise HTTPException(status_code=404, detail=detail)
    return cap


# Static frontend mounting if built
DIST_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if DIST_DIR.exists() and (DIST_DIR / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=str(DIST_DIR / "assets")), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        file_path = DIST_DIR / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(DIST_DIR / "index.html")

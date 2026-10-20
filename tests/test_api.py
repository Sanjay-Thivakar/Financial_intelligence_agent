"""
Test Suite for Financial Intelligence Agent Dashboard API & Research Invariants.

Verifies:
1. Eligible companies catalog & AA exclusion guardrails.
2. Market quotes & technical feature computation schemas.
3. Walk-forward model evaluation metrics & provenance fidelity (Phase 5D report).
4. SEC fundamentals & News coverage truthfulness (no fabricated facts).
5. Experimental prediction inference pipeline & honest unavailable states.
"""

import pytest
from starlette.testclient import TestClient
from src.api.app import app
from src.api.schemas import (
    CompanyMetadata,
    CompanyMarketResponse,
    ModelEvaluationSummaryResponse,
    PredictionResponse,
)

client = TestClient(app)


def test_health_endpoint():
    """Verifies operational health check and research mode flag."""
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "operational"
    assert data["mode"] == "RESEARCH / EXPERIMENTAL"


def test_eligible_companies_catalog():
    """
    Verifies that the eligible company list strictly contains AAPL, JPM, GOOG, TSLA
    and that AA is strictly excluded.
    """
    res = client.get("/api/companies")
    assert res.status_code == 200
    data = res.json()
    tickers = [c["ticker"] for c in data]

    assert set(tickers) == {"AAPL", "JPM", "GOOG", "TSLA"}
    assert "AA" not in tickers

    # Validate schema for all companies
    for item in data:
        validated = CompanyMetadata.model_validate(item)
        assert validated.total_sessions > 0
        assert validated.pilot_eligible is True


def test_aa_exclusion_guardrail():
    """
    Verifies that querying excluded company AA returns HTTP 400
    with explicit documentation of corporate split ambiguity.
    """
    res = client.get("/api/companies/AA")
    assert res.status_code == 400
    detail = res.json()["detail"]
    assert "AA is excluded" in detail
    assert "corporate split" in detail

    res_mkt = client.get("/api/companies/AA/market")
    assert res_mkt.status_code == 400


def test_unknown_company_rejection():
    """Verifies that an unknown ticker returns HTTP 404."""
    res = client.get("/api/companies/XYZ_UNKNOWN")
    assert res.status_code == 404


def test_company_market_series_and_indicators():
    """
    Verifies market endpoint for AAPL:
    1. Schema conformance (OHLCV, Adjusted Close).
    2. Computed technical overlays (SMA, RSI, Volatility).
    3. Forward 5-session target computation and terminal masking.
    """
    res = client.get("/api/companies/AAPL/market?limit=100")
    assert res.status_code == 200
    data = res.json()
    validated = CompanyMarketResponse.model_validate(data)

    assert validated.ticker == "AAPL"
    assert validated.total_points == 100
    assert len(validated.series) == 100
    assert "Adjusted close" in validated.adjustment_semantics

    # Verify latest point
    latest = validated.series[-1]
    assert latest.adjusted_close > 0
    assert latest.open > 0
    assert latest.volume > 0

    # Indicators should be calculated
    assert latest.market_sma_20d is not None
    assert latest.market_sma_50d is not None
    assert latest.market_rsi_14d is not None
    assert latest.market_volatility_21d is not None


def test_sec_and_news_coverage_truthfulness():
    """
    Verifies that missing SEC facts and News remain unobserved (no fabrication):
    - AAPL and JPM have active_with_facts.
    - GOOG and TSLA have source_unavailable.
    """
    res = client.get("/api/companies")
    assert res.status_code == 200
    meta_map = {c["ticker"]: c for c in res.json()}

    # Fundamentals coverage
    assert meta_map["AAPL"]["sec_coverage_status"] == "active_with_facts"
    assert meta_map["JPM"]["sec_coverage_status"] == "active_with_facts"
    assert meta_map["GOOG"]["sec_coverage_status"] == "source_unavailable"
    assert meta_map["TSLA"]["sec_coverage_status"] == "source_unavailable"

    # News coverage
    assert meta_map["AAPL"]["news_coverage_status"] == "active_with_headlines"
    assert meta_map["JPM"]["news_coverage_status"] == "source_unavailable"
    assert meta_map["GOOG"]["news_coverage_status"] == "source_unavailable"
    assert meta_map["TSLA"]["news_coverage_status"] == "source_unavailable"


def test_model_evaluation_metrics_and_provenance():
    """
    Verifies that model evaluation scores match the audited Phase 5D walk-forward holdout results
    and preserve explicit provenance labeling.
    """
    res = client.get("/api/models/evaluation")
    assert res.status_code == 200
    data = res.json()
    validated = ModelEvaluationSummaryResponse.model_validate(data)

    # Provenance must be explicitly documented
    assert "Phase 5D" in validated.provenance
    assert "not recomputed in this session" in validated.provenance

    # Verify holdout Fold 3 metrics in the 4-company panel
    fold3_dict = next(f for f in data["fold_results"] if f["fold"] == 3)

    assert fold3_dict["zero_mae"] == 0.0536
    assert fold3_dict["median_mae"] == 0.0502
    assert fold3_dict["market_ridge_mae"] == 0.0497
    assert fold3_dict["fund_ridge_mae"] == 0.0504

    # Model 1 (Market-Only Ridge) won holdout Fold 3
    assert "0.0497" in fold3_dict["best_model_mae"]

    # Critical findings must emphasize that lower MAE does not equal trading profitability
    profitability_warning = any("trading profitability" in f for f in validated.critical_findings)
    assert profitability_warning is True


def test_model_status_endpoint():
    """Verifies that model status indicates pipeline availability and unmodeled decision layer."""
    res = client.get("/api/models/status")
    assert res.status_code == 200
    data = res.json()

    assert data["reference_0_zero_return"]["status"] == "active"
    assert data["model_1_market_ridge"]["status"] == "active"
    assert data["decision_layer"]["status"] == "unimplemented"


def test_experimental_prediction_success():
    """
    Verifies genuine forward-return prediction generation for eligible company:
    1. Returns status 'available'.
    2. Returns predicted forward return with percentage.
    3. Documents features used (17 features).
    4. Explicitly includes limitations and experimental disclaimer.
    5. Does NOT fabricate buy/sell decisions or confidence ratings.
    """
    payload = {"ticker": "AAPL"}
    res = client.post("/api/models/predict", json=payload)
    assert res.status_code == 200
    data = res.json()
    validated = PredictionResponse.model_validate(data)

    assert validated.status == "available"
    assert validated.ticker == "AAPL"
    assert validated.predicted_forward_return is not None
    assert "%" in validated.predicted_forward_return_pct
    assert len(validated.features_used) == 17
    assert validated.is_experimental is True

    # Check limitations are present
    assert len(validated.limitations) > 0
    assert any("investment recommendation" in lim.lower() for lim in validated.limitations)


def test_experimental_prediction_guardrails_on_excluded_company():
    """
    Verifies that prediction request for excluded company AA returns
    status 'unavailable' without crashing or fabricating outputs.
    """
    payload = {"ticker": "AA"}
    res = client.post("/api/models/predict", json=payload)
    assert res.status_code == 200
    data = res.json()
    validated = PredictionResponse.model_validate(data)

    assert validated.status == "unavailable"
    assert "excluded" in validated.message
    assert validated.predicted_forward_return is None

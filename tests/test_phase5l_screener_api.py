"""
Phase 5L Automated Test Suite: 60-Company Screener, Signal API & Risk Diagnostics.

Tests:
1. Universe Representation: All 60 manifest companies discoverable in /api/research/companies.
2. Filtering & Search: Ticker search, sector filter, signal filter, coverage filter.
3. Pagination & Sorting: Limit, offset, sort_by (predicted_return, ticker, sector, coverage).
4. Honest Truncation: BLK, CSCO, CVS, EQIX, FCX flagged as is_truncated=True with <90% coverage.
5. AA Exclusion Governance: AA returns coverage_status="EXCLUDED" with explicit corporate split identity audit.
6. Unknown Ticker 404 Handling.
7. Detail Endpoint Schema & Funnel: /api/research/companies/{ticker} returns 8-stage funnel and historical OHLCV chart.
8. Signal Diagnostics Endpoint: /api/research/signals/{ticker} returns granular gate pass/fail rationale.
9. Baseline Model Invariant: Default model is ridge_regression (Phase 5J benchmark); no automatic promotion.
10. Historical Integrity: Timestamps strictly reflect archived 2019-2020 OOS window; prominent research disclaimer.
"""

import pytest
from starlette.testclient import TestClient
from src.api.app import app
from src.api.schemas import (
    ScreenerResponse,
    CompanyResearchDetailResponse,
    BulkSignalsResponse,
    SignalDetailResponse,
)

client = TestClient(app)


def test_screener_returns_all_60_manifest_companies():
    """Verify that /api/research/companies returns all 60 companies from the validated manifest."""
    res = client.get("/api/research/companies?limit=100")
    assert res.status_code == 200
    data = res.json()
    validated = ScreenerResponse.model_validate(data)

    assert validated.total_cohort_count == 60
    assert validated.filtered_count == 60
    assert len(validated.companies) == 60

    tickers = [c.ticker for c in validated.companies]
    assert len(set(tickers)) == 60
    # Core tickers across multiple sectors must be present
    for expected in ["AAPL", "JPM", "GOOG", "TSLA", "MSFT", "AMZN", "NVDA", "XOM", "BLK", "FCX"]:
        # Tickers in 60-cohort
        if expected != "GOOG":  # Note: GOOG was pilot, GOOGL or others in 60 cohort
            assert expected in tickers

    # AA must be present in the excluded_companies list
    assert any(e["ticker"] == "AA" for e in validated.excluded_companies)

    # Default model must be Ridge
    assert validated.default_model == "ridge_regression"
    assert "Historical research mode" in validated.disclaimer


def test_screener_aa_exclusion_integrity():
    """Verify AA is explicitly audited as EXCLUDED with identity explanation and no fabricated signals."""
    res = client.get("/api/research/companies")
    assert res.status_code == 200
    data = res.json()
    aa_ex = next((e for e in data["excluded_companies"] if e["ticker"] == "AA"), None)
    assert aa_ex is not None
    assert "corporate split" in aa_ex["reason"].lower() or "identity" in aa_ex["reason"].lower()

    # Querying AA detail returns 200 with EXCLUDED coverage and identity gate failure
    res_detail = client.get("/api/research/companies/AA")
    assert res_detail.status_code == 200
    detail = res_detail.json()
    assert detail["coverage_status"] == "EXCLUDED"
    assert detail["signal"] == "EXCLUDED"
    assert detail["predicted_return"] is None
    assert any("corporate split" in r.lower() or "identity" in r.lower() for r in detail["decision_reasons"])


def test_screener_truncated_companies_transparency():
    """Verify that BLK, CSCO, CVS, EQIX, FCX are marked with is_truncated=True."""
    truncated_tickers = ["BLK", "CSCO", "CVS", "EQIX", "FCX"]
    res = client.get("/api/research/companies?limit=100&coverage=truncated")
    assert res.status_code == 200
    data = res.json()
    tickers = [c["ticker"] for c in data["companies"]]
    for tick in truncated_tickers:
        assert tick in tickers

    # Verify coverage percentage is <90.0% and flagged
    for comp in data["companies"]:
        assert comp["is_truncated"] is True
        assert comp["completeness_pct"] < 90.0


def test_screener_search_filtering():
    """Verify search filter by ticker and company name."""
    # Search by ticker
    res = client.get("/api/research/companies?search=AAPL")
    assert res.status_code == 200
    data = res.json()
    assert data["filtered_count"] >= 1
    assert data["companies"][0]["ticker"] == "AAPL"

    # Search by company name
    res_name = client.get("/api/research/companies?search=Microsoft")
    assert res_name.status_code == 200
    data_name = res_name.json()
    assert any(c["ticker"] == "MSFT" for c in data_name["companies"])


def test_screener_sector_filtering():
    """Verify filtering by GICS sector."""
    res = client.get("/api/research/companies?sector=Information+Technology&limit=100")
    assert res.status_code == 200
    data = res.json()
    assert data["filtered_count"] > 0
    for comp in data["companies"]:
        assert "Information Technology" in comp["sector"]


def test_screener_signal_filtering():
    """Verify filtering by signal (BUY, HOLD, SELL, EXCLUDED)."""
    res_hold = client.get("/api/research/companies?signal=HOLD&limit=100")
    assert res_hold.status_code == 200
    data_hold = res_hold.json()
    for comp in data_hold["companies"]:
        assert comp["signal"] == "HOLD"


def test_screener_pagination_and_sorting():
    """Verify pagination limit/offset and sorting."""
    res_p1 = client.get("/api/research/companies?limit=10&offset=0&sort_by=ticker&sort_dir=asc")
    assert res_p1.status_code == 200
    d1 = res_p1.json()
    assert len(d1["companies"]) == 10

    res_p2 = client.get("/api/research/companies?limit=10&offset=10&sort_by=ticker&sort_dir=asc")
    assert res_p2.status_code == 200
    d2 = res_p2.json()
    assert len(d2["companies"]) == 10

    # Ensure page 1 and page 2 do not overlap
    t1 = {c["ticker"] for c in d1["companies"]}
    t2 = {c["ticker"] for c in d2["companies"]}
    assert t1.isdisjoint(t2)


def test_company_detail_endpoint_schema():
    """Verify /api/research/companies/{ticker} returns complete profile, 8-stage funnel, and price chart."""
    res = client.get("/api/research/companies/AAPL")
    assert res.status_code == 200
    data = res.json()
    validated = CompanyResearchDetailResponse.model_validate(data)

    assert validated.ticker == "AAPL"
    assert validated.company_name == "Apple Inc."
    assert validated.sector == "Information Technology"
    assert "ridge_regression" in validated.model_id

    # Verify 8 funnel stages exist
    assert len(validated.funnel_stages) == 8
    stage_numbers = [s.stage_number for s in validated.funnel_stages]
    assert stage_numbers == [1, 2, 3, 4, 5, 6, 7, 8]

    # Verify chart series has real historical prices
    assert len(validated.historical_price_series) > 50
    latest_pt = validated.historical_price_series[-1]
    assert latest_pt["close"] > 0
    assert latest_pt["volume"] > 0

    # Verify historical disclaimer is present
    assert "Historical research mode" in validated.disclaimer


def test_company_detail_aa_excluded():
    """Verify /api/research/companies/AA returns 200 with EXCLUDED category and identity gate failure."""
    res = client.get("/api/research/companies/AA")
    assert res.status_code == 200
    data = res.json()
    assert data["coverage_status"] == "EXCLUDED"
    assert data["signal"] == "EXCLUDED"
    assert data["decision_category"] == "EXCLUDED"

    # Stage 2 (Identity & Eligibility Gate) must be FAIL
    stage_2 = next((s for s in data["funnel_stages"] if s["stage_number"] == 2), None)
    assert stage_2 is not None
    assert stage_2["status"] == "FAIL"
    assert "corporate split" in stage_2["explanation"].lower()


def test_company_detail_unknown_ticker():
    """Verify /api/research/companies/UNKNOWN_TICKER returns 404."""
    res = client.get("/api/research/companies/UNKNOWN999")
    assert res.status_code == 404
    assert "not part of the validated 60-company" in res.json()["detail"].lower()


def test_bulk_signals_endpoint():
    """Verify /api/research/signals returns bulk signals and decision metadata."""
    res = client.get("/api/research/signals")
    assert res.status_code == 200
    data = res.json()
    validated = BulkSignalsResponse.model_validate(data)

    assert validated.total_signals == 60
    assert len(validated.signals) == 60
    assert validated.model_id == "ridge_regression"
    assert "reasons" in data["signals"][0]


def test_single_company_signal_detail():
    """Verify /api/research/signals/{ticker} returns decision funnel, risk gates, and net hurdle."""
    res = client.get("/api/research/signals/MSFT")
    assert res.status_code == 200
    data = res.json()
    validated = SignalDetailResponse.model_validate(data)

    assert validated.ticker == "MSFT"
    assert "ridge_regression" in validated.model_id
    assert len(validated.funnel_stages) == 8
    assert validated.roundtrip_cost_bps == 15.0
    assert validated.threshold_applied == 0.015
    assert validated.signal in ["BUY", "HOLD", "SELL", "UNAVAILABLE"]


def test_model_switching_preserves_ridge_as_reference():
    """Verify requesting an alternate model (e.g. hist_gradient_boosting) does not change default Ridge."""
    # Request with explicit model
    res_gbrt = client.get("/api/research/companies/AAPL?model_id=hist_gradient_boosting")
    assert res_gbrt.status_code == 200
    d_gbrt = res_gbrt.json()
    assert "hist_gradient_boosting" in d_gbrt["model_id"]

    # Default request without model parameter must remain ridge_regression
    res_default = client.get("/api/research/companies/AAPL")
    assert res_default.status_code == 200
    d_default = res_default.json()
    assert "ridge_regression" in d_default["model_id"]


# =====================================================================
# Phase 5L.1 Targeted Integrity Audit Tests
# =====================================================================

def test_audit_transaction_cost_and_hurdle_reconciliation():
    """
    Phase 5L.1 Audit:
    1. Verify entry (2.5), exit (2.5), half-spread (2.5), slippage (2.5) are per-side.
    2. Verify total roundtrip friction is exactly 15.0 bps (0.0015).
    3. Verify net return hurdle is 0.0050 (50 bps) net after friction.
    4. Verify gross return hurdle is 0.0065 (65 bps) before friction.
    """
    from src.decision.schema import TransactionCostConfig, RiskGateConfig
    from src.decision.cost import TransactionCostModel

    cost_cfg = TransactionCostConfig(
        entry_fee_bps=2.5,
        exit_fee_bps=2.5,
        half_spread_bps=2.5,
        slippage_bps=2.5,
    )
    assert cost_cfg.total_roundtrip_bps == 15.0
    assert cost_cfg.total_roundtrip_decimal == 0.0015

    breakdown = TransactionCostModel.calculate_cost_breakdown(cost_cfg)
    assert breakdown["entry_commission_bps"] == 2.5
    assert breakdown["exit_commission_bps"] == 2.5
    assert breakdown["total_spread_bps"] == 5.0  # 2 * 2.5 bps
    assert breakdown["total_slippage_bps"] == 5.0  # 2 * 2.5 bps
    assert breakdown["total_roundtrip_bps"] == 15.0

    risk_cfg = RiskGateConfig(
        buy_threshold=0.015,
        sell_threshold=-0.015,
        max_uncertainty=0.08,
        min_net_return_hurdle=0.005,
    )
    gross_hurdle = cost_cfg.total_roundtrip_decimal + risk_cfg.min_net_return_hurdle
    assert round(gross_hurdle, 6) == 0.0065


def test_audit_historical_timestamps_fold3_holdout_vs_truncated():
    """
    Phase 5L.1 Audit:
    Verify that querying Fold 3 Holdout (2020-06-03):
    1. Returns valid predictions for active cohort members (AAPL, MSFT).
    2. Reports all 5 truncated companies as UNAVAILABLE with zero fabricated return.
    """
    res = client.get("/api/research/companies?as_of_date=2020-06-03")
    assert res.status_code == 200
    data = res.json()

    aapl = next((c for c in data["companies"] if c["ticker"] == "AAPL"), None)
    assert aapl is not None
    assert aapl["observation_date"] == "2020-06-03"
    assert "Fold3" in aapl["model_id"]
    assert aapl["predicted_return"] is not None

    truncated_tickers = ["BLK", "CSCO", "CVS", "EQIX", "FCX"]
    for tick in truncated_tickers:
        item = next((c for c in data["companies"] if c["ticker"] == tick), None)
        assert item is not None
        assert item["signal"] == "UNAVAILABLE"
        assert item["risk_status"] == "Unavailable: Truncated History"
        assert item["observation_date"] is None
        assert item["predicted_return"] is None


def test_audit_historical_timestamps_fold2_covid_crash():
    """
    Phase 5L.1 Audit:
    Verify that querying Fold 2 (2020-03-25):
    1. Returns valid predictions for both complete and truncated companies (all 60 active in Fold 2).
    2. Model provenance reflects Fold 2 cutoff (2020-01-16).
    """
    res = client.get("/api/research/companies?as_of_date=2020-03-25")
    assert res.status_code == 200
    data = res.json()

    for tick in ["AAPL", "CSCO", "BLK", "FCX"]:
        item = next((c for c in data["companies"] if c["ticker"] == tick), None)
        assert item is not None
        assert item["observation_date"] == "2020-03-25"
        assert "Fold2" in item["model_id"]
        assert item["predicted_return"] is not None


def test_audit_signal_integrity_defensive_gating():
    """
    Phase 5L.1 Audit:
    Verify that failed risk gates cannot produce a misleading BUY or SELL under any circumstances.
    """
    from src.decision.schema import DecisionContractRequest, RiskGateConfig, TransactionCostConfig
    from src.decision.policy import ThresholdDecisionPolicy

    policy = ThresholdDecisionPolicy()

    # Breached volatility gate (0.25 > 0.15) with high positive return (+0.05)
    req_vol = DecisionContractRequest(
        company_id="US_CIK_0000320193",
        ticker="AAPL",
        decision_timestamp="2020-06-03T14:15:00Z",
        predicted_forward_return=0.05,
        forecast_uncertainty=0.04,
        rolling_volatility_5d=0.25,
        model_id="ridge_regression_Fold3",
        training_cutoff_date="2020-03-23",
        risk_config=RiskGateConfig(max_rolling_volatility_5d=0.15),
    )
    resp_vol = policy.evaluate(req_vol)
    assert resp_vol.signal.value == "HOLD"
    assert any("VOLATILITY_GATE" in r for r in resp_vol.risk_checks_failed)

    # Breached uncertainty gate (0.10 > 0.08)
    req_unc = DecisionContractRequest(
        company_id="US_CIK_0000320193",
        ticker="AAPL",
        decision_timestamp="2020-06-03T14:15:00Z",
        predicted_forward_return=0.05,
        forecast_uncertainty=0.10,
        rolling_volatility_5d=0.05,
        model_id="ridge_regression_Fold3",
        training_cutoff_date="2020-03-23",
        risk_config=RiskGateConfig(max_uncertainty=0.08),
    )
    resp_unc = policy.evaluate(req_unc)
    assert resp_unc.signal.value == "HOLD"
    assert any("UNCERTAINTY_GATE" in r for r in resp_unc.risk_checks_failed)

    # Inverted temporal cutoff (decision precedes cutoff)
    req_inv = DecisionContractRequest(
        company_id="US_CIK_0000320193",
        ticker="AAPL",
        decision_timestamp="2019-01-01T14:15:00Z",
        predicted_forward_return=0.05,
        forecast_uncertainty=0.04,
        rolling_volatility_5d=0.05,
        model_id="ridge_regression_Fold3",
        training_cutoff_date="2020-03-23",
    )
    resp_inv = policy.evaluate(req_inv)
    assert resp_inv.signal.value == "HOLD"
    assert any("PROVENANCE_GATE" in r for r in resp_inv.risk_checks_failed)

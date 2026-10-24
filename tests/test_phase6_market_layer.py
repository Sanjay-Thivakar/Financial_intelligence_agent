"""
Phase 6.3 Automated Test Suite: Unified Market Data Layer Harmonization.

Verifies:
1. Expanded Cohort Market Data Access:
   - CAT, MSFT, and NVDA return HTTP 200 with verified market observations from Phase 5I artifacts.
   - Conforms strictly to CompanyMarketResponse schema.
   - Technical indicators (SMA20, SMA50, RSI14, Volatility21) and 5-session forward targets are computed.
   - Rows are chronologically ordered.
   - Data source identifies Phase 5I market expansion.
2. Legacy Prototype Compatibility:
   - GET /api/companies returns strictly the original 4 prototype companies.
   - AAPL, JPM, GOOG, and TSLA market requests preserve established Tiingo prototype source.
   - AA exclusion strictly returns HTTP 400 with corporate-split explanation.
   - GOOGL does not resolve to GOOG market data (returns HTTP 404).
   - Unknown tickers (XYZ_UNKNOWN) return HTTP 404.
3. Data Integrity & Error Handling:
   - Missing market artifact does not fabricate data (returns HTTP 404).
   - Missing required market columns produces HTTP 400.
   - Duplicate trading dates produces HTTP 400.
   - Null trading dates produces HTTP 400.
   - A ticker outside the validated cohort (SPY) is rejected with HTTP 404 even if mock market data exists.
4. Cross-Source Invariance:
   - Market availability does not grant runtime inference or portfolio simulation support.
   - Capability contract fold eligibility and screener behavior remain invariant.
"""

from pathlib import Path
import pytest
import pandas as pd
from starlette.testclient import TestClient

from src.api.app import app
from src.api.service import DashboardService, dashboard_service
from src.api.schemas import (
    CompanyMarketResponse,
    MarketSeriesPoint,
    CapabilityStatus,
)

client = TestClient(app)


# =====================================================================
# 1. Expanded Cohort Market Data Access
# =====================================================================

def test_cat_expanded_market_data_access():
    """Verify that CAT returns HTTP 200 with Phase 5I market observations and computed indicators."""
    res = client.get("/api/companies/CAT/market?limit=50")
    assert res.status_code == 200
    data = res.json()
    validated = CompanyMarketResponse.model_validate(data)

    assert validated.ticker == "CAT"
    assert validated.company_id == "US_CIK_0000018230"
    assert validated.company_name == "Caterpillar Inc."
    assert "Phase 5I" in validated.data_source
    assert validated.total_points == 50
    assert len(validated.series) == 50

    # Verify chronological ordering
    dates = [pt.trading_date for pt in validated.series]
    assert dates == sorted(dates)

    # Verify latest point
    latest = validated.series[-1]
    assert latest.trading_date == "2023-12-28"
    assert latest.close > 0
    assert latest.adjusted_close > 0
    assert latest.volume > 0

    # Verify computed indicators
    assert latest.market_sma_20d is not None
    assert latest.market_sma_50d is not None
    assert latest.market_rsi_14d is not None
    assert latest.market_volatility_21d is not None
    assert latest.target_forward_return_5d_valid is False  # Terminal masking prevents future leakage


def test_msft_expanded_market_data_access():
    """Verify that MSFT returns HTTP 200 with Phase 5I market observations."""
    res = client.get("/api/companies/MSFT/market?limit=100")
    assert res.status_code == 200
    data = res.json()
    validated = CompanyMarketResponse.model_validate(data)

    assert validated.ticker == "MSFT"
    assert validated.company_id == "US_CIK_0000789019"
    assert validated.company_name == "Microsoft"
    assert "Phase 5I" in validated.data_source
    assert validated.total_points == 100
    assert len(validated.series) == 100
    assert validated.latest_observation_date == "2023-12-28"


def test_nvda_expanded_market_data_access():
    """Verify that NVDA returns HTTP 200 with Phase 5I market observations."""
    res = client.get("/api/companies/NVDA/market?limit=100")
    assert res.status_code == 200
    data = res.json()
    validated = CompanyMarketResponse.model_validate(data)

    assert validated.ticker == "NVDA"
    assert validated.company_id == "US_CIK_0001045810"
    assert validated.company_name == "Nvidia"
    assert "Phase 5I" in validated.data_source
    assert validated.total_points == 100
    assert len(validated.series) == 100
    assert validated.latest_observation_date == "2023-12-28"


def test_market_endpoint_date_filtering():
    """Verify that start_date and end_date filtering work correctly on expanded cohort."""
    res = client.get("/api/companies/CAT/market?start_date=2020-01-02&end_date=2020-01-31&limit=500")
    assert res.status_code == 200
    data = res.json()
    validated = CompanyMarketResponse.model_validate(data)

    assert validated.total_points == 21  # 21 trading sessions in Jan 2020
    assert validated.series[0].trading_date == "2020-01-02"
    assert validated.series[-1].trading_date == "2020-01-31"
    for pt in validated.series:
        assert "2020-01-02" <= pt.trading_date <= "2020-01-31"


# =====================================================================
# 2. Legacy Prototype Compatibility
# =====================================================================

def test_legacy_companies_catalog_invariance():
    """
    CRITICAL: Verify that /api/companies continues to return ONLY the four prototype companies
    and has not been expanded.
    """
    res = client.get("/api/companies")
    assert res.status_code == 200
    data = res.json()
    tickers = [c["ticker"] for c in data]

    assert set(tickers) == {"AAPL", "JPM", "GOOG", "TSLA"}
    assert "CAT" not in tickers
    assert "MSFT" not in tickers
    assert "NVDA" not in tickers
    assert len(data) == 4


def test_legacy_prototype_market_endpoint_source_preservation():
    """
    Verify that prototype companies (AAPL, JPM, GOOG, TSLA) continue to use the
    established Tiingo prototype sample source.
    """
    for ticker in ["AAPL", "JPM", "GOOG", "TSLA"]:
        res = client.get(f"/api/companies/{ticker}/market?limit=50")
        assert res.status_code == 200
        data = res.json()
        assert data["ticker"] == ticker
        assert "Prototype S&P 500 Market Sample" in data["data_source"]
        assert len(data["series"]) == 50


def test_aa_exclusion_guardrail():
    """Verify that querying excluded company AA returns HTTP 400 with corporate split detail."""
    res = client.get("/api/companies/AA/market")
    assert res.status_code == 400
    assert "AA is excluded" in res.json()["detail"]
    assert "corporate split" in res.json()["detail"].lower()


def test_googl_distinct_share_class_rejection():
    """
    Verify that querying GOOGL does NOT resolve to GOOG market data.
    Must return HTTP 404 with explicit share-class explanation.
    """
    res = client.get("/api/companies/GOOGL/market")
    assert res.status_code == 404
    detail = res.json()["detail"]
    assert "distinct share class" in detail.lower()
    assert "GOOGL" in detail
    assert "not interchangeable" in detail.lower()


def test_unknown_ticker_rejection():
    """Verify that an unknown ticker outside the universe returns HTTP 404."""
    res = client.get("/api/companies/XYZ_UNKNOWN/market")
    assert res.status_code == 404
    assert "not available" in res.json()["detail"]


# =====================================================================
# 3. Data Integrity & Error Handling (Isolated Tests)
# =====================================================================

def test_missing_market_artifact_returns_404(monkeypatch, tmp_path):
    """Verify that missing market artifact does not fabricate data, returning HTTP 404."""
    srv = DashboardService()
    srv._ensure_capabilities_initialized()

    fake_dir = tmp_path / "empty_dir"
    fake_dir.mkdir()
    monkeypatch.setattr("src.api.service.DATA_DIR", fake_dir)

    # Attempt to load an uncached expanded ticker
    res = srv.get_company_market("CAT")
    assert res is None


def test_missing_required_market_columns_raises_error(monkeypatch, tmp_path):
    """Verify that missing required market columns (e.g. adjusted_close) raises ValueError."""
    srv = DashboardService()
    srv._ensure_capabilities_initialized()

    p_mkt = tmp_path / "market" / "phase5i"
    p_mkt.mkdir(parents=True)
    # Write a corrupt parquet missing 'adjusted_close'
    corrupt_df = pd.DataFrame({
        "trading_date": ["2020-01-02", "2020-01-03"],
        "open": [100.0, 101.0],
        "high": [105.0, 106.0],
        "low": [99.0, 100.0],
        "close": [104.0, 105.0],
        "volume": [1000.0, 1100.0],
    })
    corrupt_df.to_parquet(p_mkt / "CAT.parquet")

    monkeypatch.setattr("src.api.service.DATA_DIR", tmp_path)
    # Clear in-memory cache for CAT
    srv._feature_data_cache.pop("CAT", None)

    with pytest.raises(ValueError) as exc:
        srv.get_company_market("CAT")
    assert "missing required columns" in str(exc.value)
    assert "adjusted_close" in str(exc.value)


def test_null_trading_dates_raises_error(monkeypatch, tmp_path):
    """Verify that null trading dates in market artifact raise ValueError."""
    srv = DashboardService()
    srv._ensure_capabilities_initialized()

    p_mkt = tmp_path / "market" / "phase5i"
    p_mkt.mkdir(parents=True)
    corrupt_df = pd.DataFrame({
        "trading_date": ["2020-01-02", None],
        "open": [100.0, 101.0],
        "high": [105.0, 106.0],
        "low": [99.0, 100.0],
        "close": [104.0, 105.0],
        "adjusted_close": [104.0, 105.0],
        "volume": [1000.0, 1100.0],
    })
    corrupt_df.to_parquet(p_mkt / "CAT.parquet")

    monkeypatch.setattr("src.api.service.DATA_DIR", tmp_path)
    srv._feature_data_cache.pop("CAT", None)

    with pytest.raises(ValueError) as exc:
        srv.get_company_market("CAT")
    assert "Null trading dates detected" in str(exc.value)


def test_duplicate_trading_dates_raises_error(monkeypatch, tmp_path):
    """Verify that duplicate trading dates raise ValueError rather than corrupting series."""
    srv = DashboardService()
    srv._ensure_capabilities_initialized()

    p_mkt = tmp_path / "market" / "phase5i"
    p_mkt.mkdir(parents=True)
    corrupt_df = pd.DataFrame({
        "trading_date": ["2020-01-02", "2020-01-02"],
        "open": [100.0, 101.0],
        "high": [105.0, 106.0],
        "low": [99.0, 100.0],
        "close": [104.0, 105.0],
        "adjusted_close": [104.0, 105.0],
        "volume": [1000.0, 1100.0],
    })
    corrupt_df.to_parquet(p_mkt / "CAT.parquet")

    monkeypatch.setattr("src.api.service.DATA_DIR", tmp_path)
    srv._feature_data_cache.pop("CAT", None)

    with pytest.raises(ValueError) as exc:
        srv.get_company_market("CAT")
    assert "Duplicate market observations detected" in str(exc.value)


def test_ticker_in_market_data_but_absent_from_validated_cohort():
    """
    Verify that an unvalidated ticker (SPY) is rejected even if market data exists on disk.
    Cohort membership is strictly validated via the capability contract.
    """
    res = client.get("/api/companies/SPY/market")
    assert res.status_code == 404
    assert "not available" in res.json()["detail"]


# =====================================================================
# 4. Cross-Source & Boundary Invariance
# =====================================================================

def test_market_data_availability_does_not_grant_runtime_inference():
    """
    Verify that serving market data for CAT does NOT falsely grant runtime inference
    or portfolio simulation eligibility in the capability contract.
    """
    # 1. Market data is available
    res_mkt = client.get("/api/companies/CAT/market?limit=10")
    assert res_mkt.status_code == 200

    # 2. Capability contract remains strictly UNVERIFIED for simulation and False for runtime inference
    res_cap = client.get("/api/v1/companies/capabilities/CAT")
    assert res_cap.status_code == 200
    cap = res_cap.json()

    assert cap["runtime"]["runtime_inference_supported"] is False
    assert cap["runtime"]["runtime_inference_model"] is None
    assert cap["runtime"]["portfolio_simulation_status"] == "UNVERIFIED"
    assert cap["runtime"]["interactive_trade_execution"] is False
    assert cap["evaluation_tracks"]["eligible_folds"] == [0, 1, 2, 3]


def test_screener_api_behavior_remains_invariant():
    """Verify that screener functionality continues to operate deterministically."""
    res = client.get("/api/research/companies?limit=10")
    assert res.status_code == 200
    data = res.json()
    assert data["total_cohort_count"] == 60
    assert len(data["companies"]) == 10

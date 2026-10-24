"""
Phase 6.2.1 Automated Test Suite: Canonical Company Universe and Capability Contract Semantics.

Verifies:
1. API structure and backward compatibility:
   - GET /api/v1/companies/capabilities returns all 60 manifest companies deterministically.
   - GET /api/v1/companies/capabilities/{ticker} matches list item and handles 404s.
   - Legacy GET /api/companies remains strictly unchanged with 4 pilot companies.
   - Legacy AA exclusion remains unchanged (HTTP 400 on /api/companies/AA, documented in capabilities).
2. Entity identity and share-class separation:
   - GOOG resolves to canonical ticker GOOG with CIK 0001652044 and related_share_classes=['GOOGL'].
   - GOOGL does NOT resolve as an alias; it returns HTTP 404 with explicit share-class explanation.
3. Market artifact vs. Evaluation-window coverage separation:
   - Raw market artifact coverage reflects physical parquet store (e.g. CAT has 13,618 sessions).
   - Evaluation-window coverage reflects Phase 5J walk-forward window (363 sessions denominator).
   - Authoritative fold eligibility matches Phase 5J manifest directly.
   - Descriptive completeness labels do not silently alter fold eligibility (e.g. BMY).
4. Portfolio simulation and execution boundaries:
   - Portfolio simulation capability is explicitly UNVERIFIED with batch-only limitation notes.
   - Interactive live trade execution is strictly False.
   - Archived prediction availability does not imply runtime inference or portfolio simulation eligibility.
5. Multi-modal and modality boundaries:
   - Modality statuses distinguish NOT_DOWNLOADED_IN_PILOT from confirmed zero values.
   - Excluded news text remains EXCLUDED_BY_POLICY.
6. Robustness against malformed sources and missing artifacts:
   - Missing required manifest columns raises ValueError.
   - Missing manifest file raises FileNotFoundError.
   - Missing market or prediction artifacts set status to UNAVAILABLE without false SUPPORTED claims.
   - Ticker present in manifest but absent from market artifact is marked UNAVAILABLE.
   - Ticker present in market data but absent from validated cohort returns 404.
"""

from pathlib import Path
import pytest
import pandas as pd
from pydantic import ValidationError
from starlette.testclient import TestClient

from src.api.app import app
from src.api.service import DashboardService, dashboard_service
from src.api.schemas import (
    CapabilityStatus,
    MarketCoverageStatus,
    IdentityStatus,
    CompanyCapabilityItem,
    CompanyCapabilityListResponse,
    CompanyIdentity,
)

client = TestClient(app)


# =====================================================================
# 1. API Structure & Backward Compatibility Tests
# =====================================================================

def test_capabilities_list_returns_all_60_manifest_companies():
    """Verify that the list endpoint returns exactly the 60 companies in the validated manifest."""
    res = client.get("/api/v1/companies/capabilities")
    assert res.status_code == 200
    data = res.json()
    validated = CompanyCapabilityListResponse.model_validate(data)

    assert validated.status == "success"
    assert validated.version == "v1"
    assert validated.total_cohort_count == 60
    assert len(validated.companies) == 60

    tickers = [c.identity.canonical_ticker for c in validated.companies]
    assert len(set(tickers)) == 60
    # Core tickers across multiple sectors must be present
    for expected in ["AAPL", "JPM", "GOOG", "TSLA", "CAT", "MSFT", "AMZN", "NVDA", "XOM", "BLK", "FCX"]:
        assert expected in tickers

    # Excluded entity AA must be documented in excluded_entities
    assert any(e["ticker"] == "AA" for e in validated.excluded_entities)


def test_capabilities_list_deterministic_ordering():
    """Verify that multiple calls produce identical, deterministically sorted output."""
    res1 = client.get("/api/v1/companies/capabilities").json()
    res2 = client.get("/api/v1/companies/capabilities").json()

    tickers1 = [c["identity"]["canonical_ticker"] for c in res1["companies"]]
    tickers2 = [c["identity"]["canonical_ticker"] for c in res2["companies"]]

    assert tickers1 == tickers2
    assert tickers1 == sorted(tickers1)


def test_capabilities_detail_matches_list_item():
    """Verify that single-company detail matches the exact record from the list endpoint."""
    res_list = client.get("/api/v1/companies/capabilities").json()
    cat_from_list = next(c for c in res_list["companies"] if c["identity"]["canonical_ticker"] == "CAT")

    res_detail = client.get("/api/v1/companies/capabilities/CAT")
    assert res_detail.status_code == 200
    cat_detail = res_detail.json()

    assert cat_detail == cat_from_list


def test_capabilities_unknown_ticker_rejection():
    """Verify that an unknown ticker returns HTTP 404."""
    res = client.get("/api/v1/companies/capabilities/XYZ_UNKNOWN")
    assert res.status_code == 404
    assert "not found in the validated research cohort" in res.json()["detail"]


def test_legacy_companies_endpoint_invariance():
    """
    CRITICAL BACKWARD COMPATIBILITY TEST:
    Verify that legacy /api/companies continues to return ONLY the 4 prototype companies
    with the exact legacy catalog structure and no extra tickers.
    """
    res = client.get("/api/companies")
    assert res.status_code == 200
    data = res.json()
    tickers = [c["ticker"] for c in data]

    assert set(tickers) == {"AAPL", "JPM", "GOOG", "TSLA"}
    assert "CAT" not in tickers
    assert "AA" not in tickers
    assert len(data) == 4


def test_legacy_aa_exclusion_invariance():
    """Verify that legacy /api/companies/AA returns HTTP 400 with corporate split message."""
    res = client.get("/api/companies/AA")
    assert res.status_code == 400
    assert "AA is excluded" in res.json()["detail"]

    # In new capability API, querying AA returns 404 with documented exclusion reason
    res_cap = client.get("/api/v1/companies/capabilities/AA")
    assert res_cap.status_code == 404
    assert "corporate split" in res_cap.json()["detail"].lower()


# =====================================================================
# 2. Company Identity & GOOG/GOOGL Share-Class Separation Tests
# =====================================================================

def test_goog_canonical_identity_resolution():
    """
    Verify GOOG has correct canonical ticker, CIK, and distinct share-class representation.
    GOOGL must NOT be listed in ticker_aliases (which would imply market instrument equivalence).
    """
    res = client.get("/api/v1/companies/capabilities/GOOG")
    assert res.status_code == 200
    data = res.json()

    identity = data["identity"]
    assert identity["canonical_ticker"] == "GOOG"
    assert identity["cik"] == "0001652044"
    assert identity["ticker_aliases"] == []  # No market instrument alias conflation
    assert identity["related_share_classes"] == ["GOOGL"]
    assert identity["share_class_description"] == "Class C (Non-voting)"
    assert identity["company_name"] == "Alphabet Inc. (Class C)"
    assert identity["sector"] == "Communication Services"
    assert "dual-class" in identity["identity_notes"].lower()


def test_googl_request_returns_404_with_precise_share_class_explanation():
    """
    Verify querying GOOGL does NOT silently resolve to GOOG market capabilities.
    Must return HTTP 404 explaining it is a distinct share class not tracked in this market cohort.
    """
    res = client.get("/api/v1/companies/capabilities/GOOGL")
    assert res.status_code == 404
    detail = res.json()["detail"]

    assert "GOOGL" in detail
    assert "distinct share class" in detail.lower()
    assert "0001652044" in detail
    assert "not interchangeable" in detail.lower()


# =====================================================================
# 3. Market Artifact Coverage vs. Evaluation-Window Coverage Separation
# =====================================================================

def test_market_artifact_vs_evaluation_window_separation_cat():
    """
    Verify CAT separates raw physical market coverage (13,618 sessions from 1970–2023)
    from Phase 5J evaluation-window coverage (363 sessions from 2019–2020).
    """
    res = client.get("/api/v1/companies/capabilities/CAT")
    assert res.status_code == 200
    data = res.json()

    mkt_art = data["market_artifact"]
    eval_win = data["evaluation_window"]
    eval_tracks = data["evaluation_tracks"]

    # 1. Market artifact coverage
    assert mkt_art["status"] == "SUPPORTED"
    assert mkt_art["total_sessions"] == 13618
    assert mkt_art["earliest_date"] == "1970-01-02"
    assert mkt_art["latest_date"] == "2023-12-28"
    assert mkt_art["source_artifact"] == "data/processed/market/phase5i_market_expansion.parquet"

    # 2. Evaluation-window coverage (Phase 5J walk-forward window)
    assert eval_win["window_start_date"] == "2019-01-02"
    assert eval_win["window_end_date"] == "2020-06-03"
    assert eval_win["expected_window_sessions"] == 363
    assert eval_win["observed_window_sessions"] == 363
    assert eval_win["completeness_pct"] == 100.0
    assert eval_win["completeness_denominator"] == 363
    assert eval_win["is_truncated"] is False
    assert eval_win["descriptive_category"] == "COMPLETE"

    # 3. Authoritative fold eligibility from manifest
    assert eval_tracks["eligible_folds"] == [0, 1, 2, 3]
    assert eval_tracks["fold_limitations"] is None


def test_market_artifact_vs_evaluation_window_separation_csco():
    """
    Verify CSCO separates raw physical market coverage (7,564 sessions from 1990–2020)
    from evaluation-window coverage (315/363 sessions, 86.78%) and Fold 3 holdout limitation.
    """
    res = client.get("/api/v1/companies/capabilities/CSCO")
    assert res.status_code == 200
    data = res.json()

    mkt_art = data["market_artifact"]
    eval_win = data["evaluation_window"]
    eval_tracks = data["evaluation_tracks"]

    # 1. Market artifact coverage
    assert mkt_art["status"] == "SUPPORTED"
    assert mkt_art["total_sessions"] == 7564
    assert mkt_art["earliest_date"] == "1990-03-26"
    assert mkt_art["latest_date"] == "2020-04-01"

    # 2. Evaluation-window coverage
    assert eval_win["window_start_date"] == "2019-01-02"
    assert eval_win["window_end_date"] == "2020-06-03"
    assert eval_win["expected_window_sessions"] == 363
    assert eval_win["observed_window_sessions"] == 315
    assert eval_win["completeness_pct"] == 86.78
    assert eval_win["completeness_denominator"] == 363
    assert eval_win["is_truncated"] is True
    assert eval_win["descriptive_category"] == "TRUNCATED"

    # 3. Fold eligibility: eligible for Folds 0, 1, 2 but NOT Fold 3
    assert eval_tracks["eligible_folds"] == [0, 1, 2]
    assert 3 not in eval_tracks["eligible_folds"]
    assert "Fold 3" in eval_tracks["fold_limitations"]


def test_descriptive_category_does_not_override_manifest_fold_eligibility_bmy():
    """
    Verify that for a near-complete company (BMY: 362/363 sessions = 99.72%),
    the descriptive label NEAR_COMPLETE does NOT alter the manifest's authoritative fold eligibility.
    BMY remains fully eligible for all 4 folds.
    """
    res = client.get("/api/v1/companies/capabilities/BMY")
    assert res.status_code == 200
    data = res.json()

    eval_win = data["evaluation_window"]
    eval_tracks = data["evaluation_tracks"]

    assert eval_win["observed_window_sessions"] == 362
    assert eval_win["completeness_pct"] == 99.72
    assert eval_win["descriptive_category"] == "NEAR_COMPLETE"
    assert eval_win["is_truncated"] is False

    # Authoritative fold eligibility from manifest remains all 4 folds
    assert eval_tracks["eligible_folds"] == [0, 1, 2, 3]


def test_all_truncated_companies_truthfulness():
    """
    Verify that all 5 truncated companies (BLK, CSCO, CVS, EQIX, FCX) are truthfully flagged.
    """
    truncated_tickers = ["BLK", "CSCO", "CVS", "EQIX", "FCX"]
    for ticker in truncated_tickers:
        res = client.get(f"/api/v1/companies/capabilities/{ticker}")
        assert res.status_code == 200
        data = res.json()

        mkt_art = data["market_artifact"]
        eval_win = data["evaluation_window"]
        eval_tracks = data["evaluation_tracks"]

        assert eval_win["is_truncated"] is True
        assert eval_win["descriptive_category"] == "TRUNCATED"
        assert eval_win["completeness_pct"] < 90.0
        assert mkt_art["latest_date"] == "2020-04-01"

        assert 0 in eval_tracks["eligible_folds"]
        assert 1 in eval_tracks["eligible_folds"]
        assert 2 in eval_tracks["eligible_folds"]
        assert 3 not in eval_tracks["eligible_folds"]
        assert "Fold 3" in eval_tracks["fold_limitations"]


# =====================================================================
# 4. Portfolio Simulation & Execution Boundaries Tests
# =====================================================================

def test_portfolio_simulation_status_unverified():
    """
    Verify that portfolio simulation capability is reported as UNVERIFIED across the cohort,
    accurately reflecting that offline batch backtesting does not establish runtime interactive eligibility.
    """
    res_list = client.get("/api/v1/companies/capabilities").json()
    for comp in res_list["companies"]:
        runtime = comp["runtime"]
        assert runtime["portfolio_simulation_status"] == "UNVERIFIED"
        assert "offline batch" in runtime["portfolio_simulation_notes"].lower()
        assert runtime["interactive_trade_execution"] is False


def test_archived_predictions_do_not_imply_runtime_inference():
    """
    Verify that archived prediction availability does NOT imply runtime inference support:
    - CAT has archived predictions across 8 models and 4 folds, but runtime_inference_supported is False.
    - AAPL is a prototype pilot ticker and has runtime_inference_supported is True.
    """
    res_cat = client.get("/api/v1/companies/capabilities/CAT").json()
    assert res_cat["predictions"]["archived_predictions_available"] is True
    assert len(res_cat["predictions"]["available_models"]) == 8
    assert res_cat["predictions"]["available_folds"] == [0, 1, 2, 3]
    assert res_cat["runtime"]["runtime_inference_supported"] is False
    assert res_cat["runtime"]["runtime_inference_model"] is None
    assert res_cat["runtime"]["portfolio_simulation_status"] == "UNVERIFIED"

    res_aapl = client.get("/api/v1/companies/capabilities/AAPL").json()
    assert res_aapl["predictions"]["archived_predictions_available"] is True
    assert res_aapl["runtime"]["runtime_inference_supported"] is True
    assert res_aapl["runtime"]["runtime_inference_model"] is not None
    assert res_aapl["runtime"]["portfolio_simulation_status"] == "UNVERIFIED"


# =====================================================================
# 5. Multi-Modal Modality & Storage Boundary Truthfulness
# =====================================================================

def test_multi_modal_status_distinctions_and_boundaries():
    """
    Verify that unobserved fundamentals/events are marked NOT_DOWNLOADED_IN_PILOT,
    preserving anti-fabrication invariants (never claiming zero values).
    """
    res_list = client.get("/api/v1/companies/capabilities").json()
    companies = res_list["companies"]

    # Track B eligible: AAPL, MSFT, JPM
    fund_supported = [c["identity"]["canonical_ticker"] for c in companies if c["multi_modal"]["sec_fundamentals_status"] == "SUPPORTED"]
    assert set(fund_supported) == {"AAPL", "MSFT", "JPM"}

    # Track C eligible: AAPL, JPM, TSLA, GOOG
    events_supported = [c["identity"]["canonical_ticker"] for c in companies if c["multi_modal"]["sec_events_status"] == "SUPPORTED"]
    assert set(events_supported) == {"AAPL", "JPM", "TSLA", "GOOG"}

    # Track D eligible: AAPL, JPM
    track_d_supported = [c["identity"]["canonical_ticker"] for c in companies if c["evaluation_tracks"]["track_d_combined"] is True]
    assert set(track_d_supported) == {"AAPL", "JPM"}

    # For CAT: fundamentals and events are NOT_DOWNLOADED_IN_PILOT
    cat = next(c for c in companies if c["identity"]["canonical_ticker"] == "CAT")
    assert cat["multi_modal"]["sec_fundamentals_status"] == "NOT_DOWNLOADED_IN_PILOT"
    assert "not downloaded" in cat["multi_modal"]["sec_fundamentals_notes"].lower()
    assert cat["multi_modal"]["sec_events_status"] == "NOT_DOWNLOADED_IN_PILOT"
    assert "not downloaded" in cat["multi_modal"]["sec_events_notes"].lower()
    assert cat["multi_modal"]["news_status"] == "EXCLUDED_BY_POLICY"


def test_provenance_sources_and_relative_paths():
    """Verify that capability records include repository-relative provenance without machine-specific paths."""
    res_cat = client.get("/api/v1/companies/capabilities/CAT").json()
    for src in res_cat["provenance_sources"]:
        assert not src.startswith("/")
        assert not src.startswith("C:")
        assert "data/processed/" in src

    assert "data/processed/universe/phase5j_company_eligibility.csv" in res_cat["provenance_sources"]
    assert "data/processed/market/phase5i_market_expansion.parquet" in res_cat["provenance_sources"]
    assert "data/processed/research/phase5k/phase5k_predictions_oos.parquet" in res_cat["provenance_sources"]


def test_schema_rejects_malformed_enum_values():
    """Verify that Pydantic validation rejects invalid capability status values."""
    with pytest.raises(ValidationError):
        CompanyIdentity(
            company_id="TEST",
            canonical_ticker="TEST",
            company_name="Test Corp",
            identity_status="INVALID_STATUS_VALUE",  # Must be IdentityStatus enum
        )


# =====================================================================
# 6. Malformed Source and Robustness Tests (Isolated / Monkeypatched)
# =====================================================================

def test_malformed_manifest_missing_required_column(monkeypatch):
    """Verify that missing a required manifest column raises ValueError rather than serving bad data."""
    srv = DashboardService()
    srv._ensure_phase5l_initialized()
    # Corrupt DataFrame by dropping required column 'window_sessions'
    corrupt_df = srv._phase5l_eligibility_df.copy().drop(columns=["window_sessions"])
    srv._phase5l_eligibility_df = corrupt_df
    srv._capabilities_initialized = False

    with pytest.raises(ValueError) as exc:
        srv._ensure_capabilities_initialized()
    assert "Eligibility manifest missing required columns" in str(exc.value)
    assert "window_sessions" in str(exc.value)


def test_missing_manifest_file_raises_error(monkeypatch):
    """Verify that a missing manifest file raises FileNotFoundError."""
    srv = DashboardService()
    srv._phase5l_initialized = True
    srv._capabilities_initialized = False

    # Point DATA_DIR to an empty non-existent directory
    fake_path = Path("non_existent_data_dir_test")
    monkeypatch.setattr("src.api.service.DATA_DIR", fake_path)

    with pytest.raises(FileNotFoundError) as exc:
        srv._ensure_capabilities_initialized()
    assert "Authoritative eligibility manifest missing" in str(exc.value)


def test_missing_market_artifact_sets_status_unavailable(monkeypatch, tmp_path):
    """
    Verify that if the physical market artifact is missing, capability builder marks
    market_artifact.status as UNAVAILABLE instead of falsely reporting SUPPORTED.
    """
    srv = DashboardService()
    srv._ensure_phase5l_initialized()
    srv._capabilities_initialized = False

    # Create dummy directory structure with valid manifest but missing market parquet
    univ_dir = tmp_path / "universe"
    univ_dir.mkdir(parents=True)
    srv._phase5l_eligibility_df.to_csv(univ_dir / "phase5j_company_eligibility.csv", index=False)

    monkeypatch.setattr("src.api.service.DATA_DIR", tmp_path)
    srv._ensure_capabilities_initialized()

    cat_cap = srv._capabilities_cache["CAT"]
    assert cat_cap.market_artifact.status == CapabilityStatus.UNAVAILABLE
    assert cat_cap.market_artifact.feature_data_available is False
    assert "unavailable" in cat_cap.market_artifact.limitations_note.lower()


def test_missing_prediction_artifact_marks_predictions_unavailable(monkeypatch, tmp_path):
    """
    Verify that if the archived prediction artifact is missing, archived_predictions_available
    is set to False and available_models is empty.
    """
    srv = DashboardService()
    srv._ensure_phase5l_initialized()
    srv._capabilities_initialized = False

    # Create directory with valid manifest and valid market parquet, but missing predictions
    univ_dir = tmp_path / "universe"
    univ_dir.mkdir(parents=True)
    srv._phase5l_eligibility_df.to_csv(univ_dir / "phase5j_company_eligibility.csv", index=False)

    mkt_dir = tmp_path / "market"
    mkt_dir.mkdir(parents=True)
    # Point market expansion to real parquet by creating a symlink/copy or reading
    real_mkt = Path("data/processed/market/phase5i_market_expansion.parquet")
    if real_mkt.exists():
        pd.read_parquet(real_mkt, columns=["ticker"]).to_parquet(mkt_dir / "phase5i_market_expansion.parquet")

    monkeypatch.setattr("src.api.service.DATA_DIR", tmp_path)
    srv._ensure_capabilities_initialized()

    cat_cap = srv._capabilities_cache["CAT"]
    assert cat_cap.predictions.archived_predictions_available is False
    assert cat_cap.predictions.available_models == []
    assert cat_cap.predictions.available_folds == []
    assert cat_cap.runtime.historical_decision_supported is False


def test_ticker_present_in_manifest_but_absent_from_market_artifact(monkeypatch, tmp_path):
    """
    Verify that a ticker present in the manifest but absent from the physical market artifact
    is marked UNAVAILABLE in market_artifact.status.
    """
    srv = DashboardService()
    srv._ensure_phase5l_initialized()
    srv._capabilities_initialized = False

    univ_dir = tmp_path / "universe"
    univ_dir.mkdir(parents=True)
    srv._phase5l_eligibility_df.to_csv(univ_dir / "phase5j_company_eligibility.csv", index=False)

    mkt_dir = tmp_path / "market"
    mkt_dir.mkdir(parents=True)
    # Write a market artifact that only has AAPL and JPM, omitting CAT
    pd.DataFrame({"ticker": ["AAPL", "JPM"], "trading_date": ["2020-01-02", "2020-01-02"]}).to_parquet(
        mkt_dir / "phase5i_market_expansion.parquet"
    )

    monkeypatch.setattr("src.api.service.DATA_DIR", tmp_path)
    srv._ensure_capabilities_initialized()

    cat_cap = srv._capabilities_cache["CAT"]
    assert cat_cap.market_artifact.status == CapabilityStatus.UNAVAILABLE
    assert cat_cap.market_artifact.feature_data_available is False
    assert "missing from physical market expansion artifact" in cat_cap.market_artifact.limitations_note.lower()


def test_ticker_in_market_data_but_absent_from_validated_cohort():
    """
    Verify that a ticker present in market data or an unverified ticker outside the cohort
    is rejected with HTTP 404.
    """
    res = client.get("/api/v1/companies/capabilities/SPY")
    assert res.status_code == 404
    assert "not found in the validated research cohort" in res.json()["detail"]


def test_missing_modality_artifact_marks_status_unavailable(monkeypatch, tmp_path):
    """
    Verify that if SEC facts artifact is missing for a company marked ELIGIBLE in manifest,
    sec_fundamentals_status falls back to UNAVAILABLE rather than falsely reporting SUPPORTED.
    """
    srv = DashboardService()
    srv._ensure_phase5l_initialized()
    srv._capabilities_initialized = False

    univ_dir = tmp_path / "universe"
    univ_dir.mkdir(parents=True)
    srv._phase5l_eligibility_df.to_csv(univ_dir / "phase5j_company_eligibility.csv", index=False)

    monkeypatch.setattr("src.api.service.DATA_DIR", tmp_path)
    srv._ensure_capabilities_initialized()

    aapl_cap = srv._capabilities_cache["AAPL"]
    # Even though AAPL is ELIGIBLE in manifest, missing local parquet forces status to UNAVAILABLE
    assert aapl_cap.multi_modal.sec_fundamentals_status == CapabilityStatus.UNAVAILABLE
    assert aapl_cap.multi_modal.sec_events_status == CapabilityStatus.UNAVAILABLE

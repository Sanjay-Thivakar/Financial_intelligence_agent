"""
Tests for Phase 6.5 — Company Archived Prediction Research Endpoints and Integrity.

Verifies:
1. Archived predictions endpoint returns genuine Phase 5K OOS predictions for expanded cohort (CAT, MSFT, NVDA).
2. Prototype cohort (AAPL, JPM, GOOG, TSLA) is fully preserved.
3. AA exclusion guardrail strictly returns HTTP 400.
4. GOOGL share-class rejection strictly returns HTTP 404.
5. Unknown tickers return HTTP 404.
6. Filtering by model_id and fold is deterministic and validated.
7. Truncated company behavior (e.g. BLK missing Fold 3) is handled honestly without fabricated rows.
8. Runtime model inference (/api/models/predict) remains unavailable for expanded cohort,
   preserving strict distinction between runtime inference and retrospective research archives.
"""

import pytest
from starlette.testclient import TestClient
from src.api.app import app

client = TestClient(app)


def test_archived_predictions_for_expanded_cohort_cat():
    """CAT is an expanded cohort member with full 4-fold OOS prediction coverage."""
    resp = client.get("/api/research/companies/CAT/predictions?limit=250")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "available"
    assert data["ticker"] == "CAT"
    assert data["company_name"] == "Caterpillar Inc."
    assert data["total_records"] == 1440  # 8 models * 180 trading dates
    assert data["returned_records"] == 250
    assert len(data["available_models"]) == 8
    assert data["available_folds"] == [0, 1, 2, 3]
    assert data["earliest_date"] == "2019-09-17"
    assert data["latest_date"] == "2020-06-03"
    assert data["is_truncated"] is False

    # Verify schema of individual prediction record
    rec = data["predictions"][0]
    assert "trading_date" in rec
    assert "fold" in rec
    assert "model_id" in rec
    assert "predicted_return" in rec
    assert "target_return" in rec
    assert "residual" in rec
    assert "sigma_train" in rec
    assert "adjusted_close" in rec
    assert rec["residual"] == pytest.approx(rec["target_return"] - rec["predicted_return"], abs=1e-5)


def test_archived_predictions_for_msft_and_nvda():
    """MSFT and NVDA both return valid historical prediction series."""
    for ticker in ["MSFT", "NVDA"]:
        resp = client.get(f"/api/research/companies/{ticker}/predictions?model_id=ridge_regression")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "available"
        assert data["ticker"] == ticker
        assert data["total_records"] == 180
        assert len(data["predictions"]) == 180
        assert all(p["model_id"] == "ridge_regression" for p in data["predictions"])


def test_archived_predictions_for_prototype_aapl():
    """AAPL prototype functionality is preserved and available in research archive."""
    resp = client.get("/api/research/companies/AAPL/predictions?model_id=ridge_regression&fold=3")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "available"
    assert data["ticker"] == "AAPL"
    assert data["total_records"] == 45
    assert len(data["predictions"]) == 45
    assert all(p["fold"] == 3 for p in data["predictions"])


def test_archived_predictions_aa_excluded():
    """AA must be rejected with HTTP 400 and corporate split explanation."""
    resp = client.get("/api/research/companies/AA/predictions")
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "Company AA is excluded" in detail
    assert "corporate split" in detail


def test_archived_predictions_googl_rejected():
    """GOOGL must be rejected with HTTP 404 and Class A share class explanation."""
    resp = client.get("/api/research/companies/GOOGL/predictions")
    assert resp.status_code == 404
    detail = resp.json()["detail"]
    assert "distinct share class" in detail
    assert "Class A voting" in detail


def test_archived_predictions_unknown_ticker():
    """Unknown ticker returns HTTP 404."""
    resp = client.get("/api/research/companies/UNKNOWN_XYZ/predictions")
    assert resp.status_code == 404
    assert "not part of the validated 60-company research cohort" in resp.json()["detail"]


def test_archived_predictions_filter_by_model_and_fold():
    """Filtering by model_id and fold returns exact deterministic subset."""
    resp = client.get("/api/research/companies/CAT/predictions?model_id=elastic_net&fold=2")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_records"] == 45
    assert all(p["model_id"] == "elastic_net" and p["fold"] == 2 for p in data["predictions"])


def test_archived_predictions_invalid_model_id():
    """Invalid model_id returns HTTP 400."""
    resp = client.get("/api/research/companies/CAT/predictions?model_id=invalid_model_xyz")
    assert resp.status_code == 400
    assert "Model identifier 'invalid_model_xyz' is invalid" in resp.json()["detail"]


def test_archived_predictions_invalid_fold():
    """Invalid fold returns HTTP 400."""
    resp = client.get("/api/research/companies/CAT/predictions?fold=99")
    assert resp.status_code == 400
    assert "Fold '99' is invalid" in resp.json()["detail"]


def test_archived_predictions_truncated_company_blk():
    """BLK has truncated coverage ending in 2020-04-01; Fold 3 is empty."""
    resp_all = client.get("/api/research/companies/BLK/predictions")
    assert resp_all.status_code == 200
    data_all = resp_all.json()
    assert data_all["is_truncated"] is True
    assert data_all["available_folds"] == [0, 1, 2]  # Fold 3 not present
    assert data_all["total_records"] == 1056

    # Specific query for Fold 3 on BLK returns empty
    resp_fold3 = client.get("/api/research/companies/BLK/predictions?fold=3")
    assert resp_fold3.status_code == 200
    data_f3 = resp_fold3.json()
    assert data_f3["status"] == "empty"
    assert data_f3["total_records"] == 0
    assert data_f3["predictions"] == []


def test_archived_predictions_distinct_from_runtime_inference():
    """
    CAT is supported in the research archive (status 200, available),
    but runtime model inference (/api/models/predict) strictly returns 'unavailable'.
    """
    # 1. Research archive endpoint
    archived_resp = client.get("/api/research/companies/CAT/predictions?limit=5")
    assert archived_resp.status_code == 200
    assert archived_resp.json()["status"] == "available"

    # 2. Runtime model inference endpoint
    runtime_resp = client.post("/api/models/predict", json={"ticker": "CAT"})
    assert runtime_resp.status_code == 200
    runtime_data = runtime_resp.json()
    assert runtime_data["status"] == "unavailable"
    assert "not in the verified experimental catalog" in runtime_data["message"]
    assert runtime_data["predicted_forward_return"] is None

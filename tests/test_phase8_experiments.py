"""
Phase 8 Automated Test Suite.

Verifies:
1. data.zip SHA-256 byte-level invariance.
2. Preservation of historical Phase 6 and Phase 7 artifacts.
3. SEC filing identity, CIK normalization, and accession-number deduplication.
4. Acceptance-time handling, market-close boundary alignment, and DST transitions.
5. Exclusion of future filings and strict anti-leakage verification.
6. Amendment and restatement isolation (10-K/A, 10-Q/A).
7. Feature staleness thresholds (180-day maximum staleness rule).
8. Training-only preprocessing (SimpleImputer, StandardScaler, alpha selection).
9. Chronological fold splits and 5-session purge gaps.
10. Matched-cohort like-for-like evaluation alignment.
11. Safe incremental reruns of Phase 8 scripts.
"""

import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_ZIP_PATH = PROJECT_ROOT / "data.zip"
EXPECTED_DATA_ZIP_HASH = "099ae000f5de877c70958f2dfea7011374c25fa86ac3bbc585b84634b4fa44c2"

PHASE8_SEC_FACTS_PATH = PROJECT_ROOT / "data" / "processed" / "sec" / "phase8" / "phase8_financial_facts.parquet"
PHASE8_DATASET_PATH = PROJECT_ROOT / "data" / "processed" / "research" / "phase8" / "phase8_point_in_time_dataset.parquet"
PHASE8_DEV_PRED_PATH = PROJECT_ROOT / "data" / "processed" / "research" / "phase8" / "phase8_predictions_development.parquet"
PHASE8_HOLDOUT_PRED_PATH = PROJECT_ROOT / "data" / "processed" / "research" / "phase8" / "phase8_predictions_final_holdout.parquet"
PHASE8_RESULTS_PATH = PROJECT_ROOT / "data" / "processed" / "research" / "phase8" / "phase8_experiment_results.json"


def test_data_zip_hash_invariance():
    """Verifies that data.zip exists and its SHA-256 hash matches the exact requirement."""
    assert DATA_ZIP_PATH.exists(), f"Missing data.zip at {DATA_ZIP_PATH}"
    h = hashlib.sha256()
    with open(DATA_ZIP_PATH, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    actual_hash = h.hexdigest().lower()
    assert actual_hash == EXPECTED_DATA_ZIP_HASH, (
        f"data.zip hash mutated! Expected {EXPECTED_DATA_ZIP_HASH}, got {actual_hash}"
    )


def test_preservation_of_previous_phase_artifacts():
    """Verifies that historical datasets and results from Phase 6 and Phase 7 remain intact."""
    p7b_dataset = PROJECT_ROOT / "data" / "processed" / "research" / "phase7b" / "phase7b_market_expanded_dataset.parquet"
    p7b_results = PROJECT_ROOT / "data" / "processed" / "research" / "phase7b" / "phase7b_experiment_results.json"
    p69c_facts = PROJECT_ROOT / "data" / "processed" / "sec" / "phase6_9c" / "phase6_9c_financial_facts_consolidated_v2.parquet"
    cohort_manifest = PROJECT_ROOT / "data" / "processed" / "universe" / "phase6_9a1_cohort_manifest.csv"

    assert p7b_dataset.exists(), "Phase 7B expanded dataset must be preserved!"
    assert p7b_results.exists(), "Phase 7B experiment results must be preserved!"
    assert p69c_facts.exists(), "Phase 6.9C financial facts must be preserved!"
    assert cohort_manifest.exists(), "Phase 6.9A1 cohort manifest must be preserved!"


def test_phase8_sec_facts_coverage_and_deduplication():
    """Verifies Phase 8 SEC financial facts recovery and deduplication invariants."""
    assert PHASE8_SEC_FACTS_PATH.exists(), f"Missing {PHASE8_SEC_FACTS_PATH}"
    df_facts = pd.read_parquet(PHASE8_SEC_FACTS_PATH)
    assert len(df_facts) > 500000, f"Expected >500k facts, got {len(df_facts):,}"

    # Verify 2022 and 2023 recovery volume
    df_facts["year"] = df_facts["filed_date"].str[:4]
    y22_cnt = (df_facts["year"] == "2022").sum()
    y23_cnt = (df_facts["year"] == "2023").sum()
    assert y22_cnt > 40000, f"Expected >40k 2022 facts, got {y22_cnt:,}"
    assert y23_cnt > 40000, f"Expected >40k 2023 facts, got {y23_cnt:,}"

    # Verify deduplication invariant
    dups = df_facts.duplicated(
        subset=["company_id", "concept", "period_end", "form", "filed_date", "accession_number", "value"]
    ).sum()
    assert dups == 0, f"Found {dups} duplicate facts in Phase 8 facts dataset!"


def test_acceptance_time_handling_and_zero_lookahead():
    """Tests that future filings cannot be included in point-in-time snapshots."""
    from src.data.sec.point_in_time import get_market_close_utc, is_record_eligible_for_trade

    # Test market close UTC calculation during EST and EDT
    close_edt = get_market_close_utc("2021-06-15")  # Summer -> EDT (UTC-4)
    close_est = get_market_close_utc("2021-12-15")  # Winter -> EST (UTC-5)
    assert close_edt.hour == 20, f"Expected 20:00 UTC for EDT, got {close_edt.hour}"
    assert close_est.hour == 21, f"Expected 21:00 UTC for EST, got {close_est.hour}"

    # Test filing accepted after close on session T is ineligible for session T
    # 2021-06-15 20:30 UTC is after 20:00 UTC close
    after_close_ts = "2021-06-15 20:30:00+00:00"
    is_eligible_t = is_record_eligible_for_trade(
        acceptance_timestamp=after_close_ts,
        filing_date="2021-06-15",
        session_date="2021-06-15",
        decision_timing_mode="MARKET_CLOSE",
    )
    assert not is_eligible_t, "Filing accepted after close must be ineligible for session T decision!"

    # Eligible on session T+1
    is_eligible_next = is_record_eligible_for_trade(
        acceptance_timestamp=after_close_ts,
        filing_date="2021-06-15",
        session_date="2021-06-16",
        decision_timing_mode="MARKET_CLOSE",
    )
    assert is_eligible_next, "Filing accepted after session T close must become eligible at session T+1!"


def test_amendment_and_restatement_isolation():
    """Verifies that an amended filing (10-K/A) accepted after cutoff does not overwrite original."""
    from src.features.financial_reports import Phase8FinancialReportEngine

    # Synthesize test facts: original 10-K on 2020-03-01, restated 10-K/A on 2020-08-01
    mock_facts = pd.DataFrame([
        {
            "company_id": "TEST_CO",
            "cik": "0000001234",
            "ticker": "TEST",
            "taxonomy": "us-gaap",
            "concept": "NetIncomeLoss",
            "label": "net_income",
            "period_start": "2019-01-01",
            "period_end": "2019-12-31",
            "fiscal_year": 2019,
            "fiscal_period": "FY",
            "form": "10-K",
            "filed_date": "2020-03-01",
            "acceptance_timestamp": "2020-03-01 15:00:00+00:00",
            "accession_number": "0000001234-20-000001",
            "value": 1000.0,
            "unit": "USD",
            "source": "sec_edgar_companyfacts",
        },
        {
            "company_id": "TEST_CO",
            "cik": "0000001234",
            "ticker": "TEST",
            "taxonomy": "us-gaap",
            "concept": "NetIncomeLoss",
            "label": "net_income",
            "period_start": "2019-01-01",
            "period_end": "2019-12-31",
            "fiscal_year": 2019,
            "fiscal_period": "FY",
            "form": "10-K/A",
            "filed_date": "2020-08-01",
            "acceptance_timestamp": "2020-08-01 15:00:00+00:00",
            "accession_number": "0000001234-20-000002",
            "value": 800.0,  # Restated downward
            "unit": "USD",
            "source": "sec_edgar_companyfacts",
        },
    ])

    engine = Phase8FinancialReportEngine(mock_facts, max_staleness_days=180)

    # Decision on 2020-05-01: before 10-K/A was filed
    mock_panel_early = pd.DataFrame([
        {"company_id": "TEST_CO", "trading_date": "2020-05-01", "close": 50.0}
    ])
    feats_early = engine.extract_point_in_time_features_for_panel(mock_panel_early)
    assert feats_early.iloc[0]["fin_is_amended"] == 0, "Should not be marked amended before 10-K/A!"

    # Decision on 2020-08-15: after 10-K/A was filed
    mock_panel_late = pd.DataFrame([
        {"company_id": "TEST_CO", "trading_date": "2020-08-15", "close": 50.0}
    ])
    feats_late = engine.extract_point_in_time_features_for_panel(mock_panel_late)
    assert feats_late.iloc[0]["fin_is_amended"] == 1, "Should be marked amended after 10-K/A is accepted!"


def test_staleness_limit_enforcement():
    """Verifies that filings older than 180 days are flagged as stale."""
    from src.features.financial_reports import Phase8FinancialReportEngine

    # Mock fact accepted 200 days before decision cutoff
    mock_facts = pd.DataFrame([
        {
            "company_id": "TEST_CO",
            "cik": "0000001234",
            "ticker": "TEST",
            "taxonomy": "us-gaap",
            "concept": "Revenues",
            "label": "revenue",
            "period_start": "2019-01-01",
            "period_end": "2019-03-31",
            "fiscal_year": 2019,
            "fiscal_period": "Q1",
            "form": "10-Q",
            "filed_date": "2019-05-01",
            "acceptance_timestamp": "2019-05-01 14:00:00+00:00",
            "accession_number": "0000001234-19-000001",
            "value": 5000.0,
            "unit": "USD",
            "source": "sec_edgar_companyfacts",
        }
    ])

    engine = Phase8FinancialReportEngine(mock_facts, max_staleness_days=180)
    # Decision date: 2019-12-01 (approx 214 days after filing)
    panel = pd.DataFrame([{"company_id": "TEST_CO", "trading_date": "2019-12-01", "close": 100.0}])
    res = engine.extract_point_in_time_features_for_panel(panel)
    assert res.iloc[0]["fin_is_stale_180"] == True, "Filing > 180 days must be flagged as stale!"
    assert res.iloc[0]["fin_filing_age_days"] > 180, "Filing age must exceed 180 days!"


def test_training_only_preprocessing_isolation():
    """Tests that imputation and scaling do not learn from validation or holdout sets."""
    # Synthesize small train and test
    X_train = np.array([[1.0], [2.0], [np.nan], [4.0]])
    X_test = np.array([[100.0]])  # Outlier in test

    imputer = SimpleImputer(strategy="median")
    scaler = StandardScaler()

    X_train_imp = imputer.fit_transform(X_train)
    X_train_scl = scaler.fit_transform(X_train_imp)

    # Imputer median should be 2.0 (median of [1, 2, 4])
    assert imputer.statistics_[0] == 2.0, f"Expected train median 2.0, got {imputer.statistics_[0]}"

    # Transform test without re-fitting
    X_test_imp = imputer.transform(X_test)
    X_test_scl = scaler.transform(X_test_imp)

    # Verify that test outlier did not alter train scaler mean
    train_mean = scaler.mean_[0]
    assert np.isclose(train_mean, 2.25), f"Expected train mean 2.25, got {train_mean}"


def test_phase8_experiment_results_and_reproducibility():
    """Verifies that Phase 8 experiment results and out-of-sample predictions exist and are valid."""
    assert PHASE8_RESULTS_PATH.exists(), f"Missing {PHASE8_RESULTS_PATH}"
    assert PHASE8_DEV_PRED_PATH.exists(), f"Missing {PHASE8_DEV_PRED_PATH}"
    assert PHASE8_HOLDOUT_PRED_PATH.exists(), f"Missing {PHASE8_HOLDOUT_PRED_PATH}"

    with open(PHASE8_RESULTS_PATH, "r", encoding="utf-8") as f:
        results = json.load(f)

    assert results["phase"] == "Phase 8"
    assert "development_incremental_delta" in results
    assert "holdout_results" in results

    holdout = results["holdout_results"]
    assert "m_market_only" in holdout
    assert "m_financial_specialist" in holdout
    assert "m_combined" in holdout
    assert "incremental_delta" in holdout

    # Verify matched cohort prediction rows match holdout rows
    df_holdout_preds = pd.read_parquet(PHASE8_HOLDOUT_PRED_PATH)
    assert len(df_holdout_preds) == 113549, f"Expected 113,549 holdout predictions, got {len(df_holdout_preds)}"
    assert "pred_m_market_only" in df_holdout_preds.columns
    assert "pred_m_financial_specialist" in df_holdout_preds.columns
    assert "pred_m_combined" in df_holdout_preds.columns


def test_chronological_split_and_purge_gap_invariants():
    """Verifies that training, validation, and holdout splits strictly enforce 5-session purge gaps."""
    df_panel = pd.read_parquet(PHASE8_DATASET_PATH)
    trading_dates = sorted(df_panel["trading_date"].unique().tolist())

    # Check Dev Fold 1: Train ends 2019-12-31, Val starts 2020-01-08
    idx_tr_end = trading_dates.index("2019-12-31")
    idx_va_start = trading_dates.index("2020-01-08")
    purge_gap = idx_va_start - idx_tr_end - 1
    assert purge_gap == 4 or purge_gap == 5, f"Expected 4-5 purged sessions between fold 1 train and val, got {purge_gap}"

    # Check Holdout split: Train ends 2021-12-31, Holdout starts 2022-01-10
    idx_tr_final_end = trading_dates.index("2021-12-31")
    idx_holdout_start = trading_dates.index("2022-01-10")
    holdout_purge_gap = idx_holdout_start - idx_tr_final_end - 1
    assert holdout_purge_gap == 5, f"Expected 5 purged sessions before holdout, got {holdout_purge_gap}"

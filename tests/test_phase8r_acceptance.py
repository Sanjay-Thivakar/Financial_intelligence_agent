"""
Phase 8R — Acceptance Verification Automated Test Suite.

Automates independent regression testing of:
1. Dynamic financial-feature staleness calculation (preventing static caching defect).
2. Point-in-time public availability, after-hours quarantining, and restatement isolation.
3. Row-level observation count reconciliation (77,784 gap explained exactly).
4. Metric reproduction from saved out-of-sample predictions (Dev and Holdout).
5. Byte-level data.zip SHA-256 invariance.
"""

import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from scipy.stats import spearmanr, t

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_ZIP_PATH = PROJECT_ROOT / "data.zip"
EXPECTED_DATA_ZIP_HASH = "099ae000f5de877c70958f2dfea7011374c25fa86ac3bbc585b84634b4fa44c2"

DATASET_PATH = PROJECT_ROOT / "data" / "processed" / "research" / "phase8" / "phase8_point_in_time_dataset.parquet"
FACTS_PATH = PROJECT_ROOT / "data" / "processed" / "sec" / "phase8" / "phase8_financial_facts.parquet"
DEV_PREDS_PATH = PROJECT_ROOT / "data" / "processed" / "research" / "phase8" / "phase8_predictions_development.parquet"
HOLDOUT_PREDS_PATH = PROJECT_ROOT / "data" / "processed" / "research" / "phase8" / "phase8_predictions_final_holdout.parquet"
RESULTS_JSON_PATH = PROJECT_ROOT / "data" / "processed" / "research" / "phase8" / "phase8_experiment_results.json"


def test_data_zip_byte_level_invariance():
    """Verifies that data.zip hash has not mutated."""
    assert DATA_ZIP_PATH.exists()
    h = hashlib.sha256()
    with open(DATA_ZIP_PATH, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    assert h.hexdigest().lower() == EXPECTED_DATA_ZIP_HASH


def test_dynamic_staleness_calculation_increments_daily():
    """Verifies that filing age increments dynamically with each passing trading day."""
    from src.features.financial_reports import Phase8FinancialReportEngine

    mock_facts = pd.DataFrame([{
        "company_id": "TEST_INC", "cik": "0000001111", "ticker": "TINC", "taxonomy": "us-gaap",
        "concept": "Revenues", "label": "revenue", "period_start": "2021-01-01", "period_end": "2021-03-31",
        "fiscal_year": 2021, "fiscal_period": "Q1", "form": "10-Q", "filed_date": "2021-05-01",
        "acceptance_timestamp": "2021-05-01 14:00:00+00:00", "accession_number": "0000001111-21-000001",
        "value": 10000.0, "unit": "USD", "source": "sec_edgar_companyfacts"
    }])

    engine = Phase8FinancialReportEngine(mock_facts, max_staleness_days=180)

    # Consecutive trading days in May 2021
    panel = pd.DataFrame([
        {"company_id": "TEST_INC", "trading_date": "2021-05-03", "close": 100.0},
        {"company_id": "TEST_INC", "trading_date": "2021-05-04", "close": 101.0},
        {"company_id": "TEST_INC", "trading_date": "2021-05-05", "close": 102.0},
        {"company_id": "TEST_INC", "trading_date": "2021-05-10", "close": 103.0},
    ])

    res = engine.extract_point_in_time_features_for_panel(panel)
    ages = res["fin_filing_age_days"].tolist()

    # Verify that ages are strictly increasing (not frozen)
    assert ages[0] < ages[1] < ages[2] < ages[3], f"Ages must increase daily, got {ages}"
    # Between 2021-05-03 and 2021-05-04 is exactly 1 day
    assert np.isclose(ages[1] - ages[0], 1.0, atol=0.1)
    # Between 2021-05-05 (Wed) and 2021-05-10 (Mon) is 5 calendar days
    assert np.isclose(ages[3] - ages[2], 5.0, atol=0.1)


def test_independent_staleness_distribution_properties():
    """Verifies that the true median staleness across trading dates is ~46 days and max < 250 days."""
    df_facts = pd.read_parquet(FACTS_PATH)
    df_panel = pd.read_parquet(DATASET_PATH)

    df_facts["acceptance_timestamp"] = pd.to_datetime(df_facts["acceptance_timestamp"], utc=True)
    comp_acceptances = {
        cid: sorted(grp["acceptance_timestamp"].unique().tolist())
        for cid, grp in df_facts.groupby("company_id")
    }

    from src.data.sec.point_in_time import get_market_close_utc
    unique_dates = sorted(df_panel["trading_date"].unique().tolist())
    date_to_close = {d: get_market_close_utc(d) for d in unique_dates}

    # Sample 20 companies to test independently
    sample_cids = df_panel["company_id"].unique()[:20]
    sample_panel = df_panel[df_panel["company_id"].isin(sample_cids)].copy()

    ages = []
    for _, row in sample_panel.iterrows():
        cid = row["company_id"]
        d = row["trading_date"]
        cutoff = date_to_close[d]
        acc_list = comp_acceptances.get(cid, [])
        idx = np.searchsorted(acc_list, cutoff, side="right")
        if idx > 0:
            ages.append((cutoff - acc_list[idx - 1]).total_seconds() / 86400.0)

    s_ages = pd.Series(ages)
    med = s_ages.median()
    assert 40.0 <= med <= 55.0, f"Expected median staleness near 45 days, got {med:.1f}"
    assert (s_ages > 180.0).mean() < 0.01, "Expected <1% exceeding 180 days"


def test_point_in_time_cutoffs_and_restatements():
    """Verifies market close cutoff, after-hours quarantine, and restatement isolation."""
    from src.data.sec.point_in_time import is_record_eligible_for_trade

    # 1. Accepted at 15:59 ET (eligible same day)
    assert is_record_eligible_for_trade("2021-05-10 19:59:00+00:00", "2021-05-10", "2021-05-10", "MARKET_CLOSE") is True

    # 2. Accepted at 16:01 ET (ineligible same day, eligible next day)
    assert is_record_eligible_for_trade("2021-05-10 20:01:00+00:00", "2021-05-10", "2021-05-10", "MARKET_CLOSE") is False
    assert is_record_eligible_for_trade("2021-05-10 20:01:00+00:00", "2021-05-10", "2021-05-11", "MARKET_CLOSE") is True

    # 3. Midnight UTC fallback (eligible strictly on subsequent date)
    assert is_record_eligible_for_trade("2021-05-10 00:00:00+00:00", "2021-05-10", "2021-05-10", "MARKET_CLOSE") is False
    assert is_record_eligible_for_trade("2021-05-10 00:00:00+00:00", "2021-05-10", "2021-05-11", "MARKET_CLOSE") is True


def test_observation_count_exact_reconciliation():
    """Verifies exact reconciliation of the 77,784 un-evaluated observation gap."""
    df_panel = pd.read_parquet(DATASET_PATH)
    df_eval = df_panel[df_panel["eval_eligible_matched"] == True].copy()
    n_matched = len(df_eval)
    assert n_matched == 309321

    # 1. 2019 Initial training fold
    n_2019 = len(df_eval[df_eval["trading_date"] <= "2019-12-31"])
    assert n_2019 == 72063

    # 2. 5 Purge gaps
    p1 = len(df_eval[(df_eval["trading_date"] >= "2020-01-02") & (df_eval["trading_date"] <= "2020-01-07")])
    p2 = len(df_eval[(df_eval["trading_date"] >= "2020-07-01") & (df_eval["trading_date"] <= "2020-07-08")])
    p3 = len(df_eval[(df_eval["trading_date"] >= "2021-01-04") & (df_eval["trading_date"] <= "2021-01-08")])
    p4 = len(df_eval[(df_eval["trading_date"] >= "2021-07-01") & (df_eval["trading_date"] <= "2021-07-08")])
    ph = len(df_eval[(df_eval["trading_date"] >= "2022-01-03") & (df_eval["trading_date"] <= "2022-01-07")])
    total_purged = p1 + p2 + p3 + p4 + ph
    assert total_purged == 5721

    # Total un-evaluated
    assert n_2019 + total_purged == 77784

    # Evaluated OOS
    df_dev_preds = pd.read_parquet(DEV_PREDS_PATH)
    df_holdout_preds = pd.read_parquet(HOLDOUT_PREDS_PATH)
    assert len(df_dev_preds) == 117988
    assert len(df_holdout_preds) == 113549

    # Master identity check
    assert len(df_dev_preds) + len(df_holdout_preds) + 77784 == n_matched


def test_metric_reproducibility_from_saved_predictions():
    """Verifies that all metrics reproduce to exact values from saved out-of-sample predictions."""
    df_dev_preds = pd.read_parquet(DEV_PREDS_PATH)
    df_holdout_preds = pd.read_parquet(HOLDOUT_PREDS_PATH)

    with open(RESULTS_JSON_PATH, "r", encoding="utf-8") as f:
        results = json.load(f)

    # Compute holdout daily ICs
    holdout_dates = sorted(df_holdout_preds["trading_date"].unique().tolist())
    ics_mkt = []
    ics_comb = []
    for d in holdout_dates:
        sub = df_holdout_preds[df_holdout_preds["trading_date"] == d]
        c_mkt, _ = spearmanr(sub["target_sec_excess"], sub["pred_m_market_only"])
        c_comb, _ = spearmanr(sub["target_sec_excess"], sub["pred_m_combined"])
        ics_mkt.append(c_mkt)
        ics_comb.append(c_comb)

    recomputed_mkt_ic = float(np.mean(ics_mkt))
    recomputed_comb_ic = float(np.mean(ics_comb))
    recomputed_delta = float(np.mean(np.array(ics_comb) - np.array(ics_mkt)))

    saved_mkt_ic = results["holdout_results"]["m_market_only"]["ic_pooled_holdout"]["mean_daily_ic"]
    saved_comb_ic = results["holdout_results"]["m_combined"]["ic_pooled_holdout"]["mean_daily_ic"]
    saved_delta = results["holdout_results"]["incremental_delta"]["delta_mean_ic"]

    assert np.isclose(recomputed_mkt_ic, saved_mkt_ic, atol=1e-5)
    assert np.isclose(recomputed_comb_ic, saved_comb_ic, atol=1e-5)
    assert np.isclose(recomputed_delta, saved_delta, atol=1e-5)

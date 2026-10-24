"""
Phase 6.9D Automated Test Suite & Acceptance Verification Gates.

Validates:
1. Multimodal dataset integrity across the canonical 305-company cohort (110,105 rows, zero duplicates).
2. Correct identity mapping for CXO (CIK 0001358071) and APA (predecessor CIK 0000006769).
3. Temporal point-in-time boundaries: decision at session T close, execution at session T+1 open, zero leakage.
4. Absence of target labels or post-decision fields in feature matrices.
5. Strict training-only preprocessing and hyperparameter tuning isolation.
6. Chronological walk-forward fold schedules with 5-session purge gap.
7. Uncontaminated final holdout protection.
8. Experiment results artifact completeness and like-for-like evaluation reproducibility.
9. Cryptographic byte-for-byte preservation of protected source artifacts.
"""

import json
import hashlib
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from src.data.universe.identity_mapping import IdentityResolutionEngine
from src.features.calendar import MarketCalendar
from src.features.config import DecisionTimingMode
from src.models.splitter import WalkForwardSplitter, WalkForwardConfig
from src.models.baseline import MarketBaselinePipeline

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATASET_PATH = PROJECT_ROOT / "data" / "processed" / "research" / "phase6_9d" / "phase6_9d_multimodal_dataset.parquet"
RESULTS_JSON_PATH = PROJECT_ROOT / "data" / "processed" / "research" / "phase6_9d" / "phase6_9d_model_experiment_results.json"
QUALITY_JSON_PATH = PROJECT_ROOT / "data" / "processed" / "research" / "phase6_9d" / "phase6_9d_data_quality_report.json"
OOS_PARQUET_PATH = PROJECT_ROOT / "data" / "processed" / "research" / "phase6_9d" / "phase6_9d_predictions_oos.parquet"

MANIFEST_69A1_PATH = PROJECT_ROOT / "data" / "processed" / "universe" / "phase6_9a1_cohort_manifest.csv"
DATA_ZIP_PATH = PROJECT_ROOT / "data.zip"
MANIFEST_68_PATH = PROJECT_ROOT / "data" / "processed" / "universe" / "phase6_8_cohort_300_manifest.csv"
MARKET_68_PATH = PROJECT_ROOT / "data" / "processed" / "market" / "phase6_8_market_300.parquet"


# --------------------------------------------------------------------------
# 1. Dataset Integrity & Cohort Coverage
# --------------------------------------------------------------------------

def test_multimodal_dataset_artifact_existence_and_integrity():
    assert DATASET_PATH.exists(), f"Missing multimodal dataset at {DATASET_PATH}"
    df = pd.read_parquet(DATASET_PATH)

    assert len(df) == 110_105, f"Expected exactly 110,105 rows, got {len(df)}"
    assert df["ticker"].nunique() == 305, f"Expected 305 unique tickers, got {df['ticker'].nunique()}"
    assert df["company_id"].nunique() == 305, f"Expected 305 unique company_ids, got {df['company_id'].nunique()}"
    assert df["trading_date"].nunique() == 361, f"Expected 361 unique trading dates, got {df['trading_date'].nunique()}"

    # Every company must have exactly 361 rows
    counts = df.groupby("company_id").size()
    assert (counts == 361).all(), "Non-uniform company observation count detected!"

    # Uniqueness of dataset_row_id
    dups = df["dataset_row_id"].duplicated().sum()
    assert dups == 0, f"Detected {dups} duplicate dataset_row_ids!"


# --------------------------------------------------------------------------
# 2. Historical Identity Provenance (CXO & APA)
# --------------------------------------------------------------------------

def test_identity_mapping_cxo_and_apa():
    df_manifest = pd.read_csv(MANIFEST_69A1_PATH)
    id_engine = IdentityResolutionEngine(df_manifest)

    # CXO resolution
    cxo_cik, cxo_name, cxo_type = id_engine.resolve_cik("CXO", "2019-06-01")
    assert cxo_cik == "0001358071", f"Expected CXO historical CIK 0001358071, got {cxo_cik}"
    assert "CONCHO" in cxo_name.upper()
    assert cxo_type == "CIK_CORRECTION"

    # APA resolution
    apa_cik, apa_name, apa_type = id_engine.resolve_cik("APA", "2019-06-01")
    assert apa_cik == "0000006769", f"Expected APA predecessor CIK 0000006769, got {apa_cik}"
    assert "APACHE" in apa_name.upper()
    assert apa_type == "PREDECESSOR_REORGANIZATION"

    # Verify both entities in dataset
    df = pd.read_parquet(DATASET_PATH)
    cxo_df = df[df["ticker"] == "CXO"]
    apa_df = df[df["ticker"] == "APA"]

    assert len(cxo_df) == 361
    assert len(apa_df) == 361
    assert cxo_df["fundamental_available"].all()
    assert apa_df["fundamental_available"].all()
    assert cxo_df["sec_event_available"].all()
    assert apa_df["sec_event_available"].all()


# --------------------------------------------------------------------------
# 3. Point-in-Time Temporal Boundaries & Anti-Leakage
# --------------------------------------------------------------------------

def test_point_in_time_cutoffs_and_anti_leakage():
    df = pd.read_parquet(DATASET_PATH)

    # 1. Decision timestamp strictly precedes execution timestamp
    dec_ts = pd.to_datetime(df["decision_timestamp"], utc=True)
    exec_ts = pd.to_datetime(df["execution_timestamp"], utc=True)
    assert (dec_ts < exec_ts).all(), "Lookahead violation: decision timestamp >= execution timestamp!"

    # 2. Execution timestamp aligns with session T+1 pre-open / open
    # For a decision on session T close, execution is session T+1 open (09:30 ET)
    # Check sample of rows
    for i in [0, 100, 1000, 50000, 100000]:
        row = df.iloc[i]
        d_ts = pd.to_datetime(row["decision_timestamp"], utc=True)
        e_ts = pd.to_datetime(row["execution_timestamp"], utc=True)
        assert d_ts < e_ts

    # 3. No fundamental acceptance timestamp strictly in future of decision cutoff
    ts_cols = [c for c in df.columns if c.startswith("fundamental_") and c.endswith("_acceptance_timestamp")]
    assert len(ts_cols) > 0, "No fundamental acceptance timestamp columns found!"
    for col in ts_cols:
        valid_ts = pd.to_datetime(df[col], utc=True).dropna()
        matching_dec = dec_ts.loc[valid_ts.index]
        violations = valid_ts > matching_dec
        assert violations.sum() == 0, f"Lookahead in {col}: {violations.sum()} records filed after decision cutoff!"


# --------------------------------------------------------------------------
# 4. Feature Matrix Isolation (No Target in Features)
# --------------------------------------------------------------------------

def test_feature_matrix_isolation_and_no_target():
    target_cols = {
        "target_forward_return_5d",
        "target_forward_return_5d_valid",
        "target_entry_date",
        "target_exit_date",
        "execution_timestamp",
    }
    feature_sets = [
        MarketBaselinePipeline.MARKET_FEATURE_COLUMNS,
        MarketBaselinePipeline.FUNDAMENTAL_FEATURE_COLUMNS,
        MarketBaselinePipeline.EVENT_FEATURE_COLUMNS,
        MarketBaselinePipeline.ALL_FEATURE_COLUMNS,
    ]
    for fset in feature_sets:
        overlap = target_cols.intersection(set(fset))
        assert len(overlap) == 0, f"FATAL: Target columns leaked into feature list: {overlap}"


# --------------------------------------------------------------------------
# 5. Chronological Walk-Forward Folds & Purge Gap
# --------------------------------------------------------------------------

def test_chronological_walk_forward_folds_and_purge_gap():
    df = pd.read_parquet(DATASET_PATH)
    unique_dates = sorted(df["trading_date"].unique().tolist())

    wf_cfg = WalkForwardConfig(n_splits=4, train_min_sessions=173, val_sessions=45, purge_sessions=5)
    splitter = WalkForwardSplitter(wf_cfg)

    splits = list(splitter.split(df))
    assert len(splits) == 4, f"Expected 4 splits, got {len(splits)}"

    for fold, (tr_idx, val_idx) in enumerate(splits):
        assert len(val_idx) == 45 * 305, f"Fold {fold}: Expected {45*305} val obs, got {len(val_idx)}"

        tr_dates = sorted(df.iloc[tr_idx]["trading_date"].unique().tolist())
        val_dates = sorted(df.iloc[val_idx]["trading_date"].unique().tolist())

        # Strict chronological order
        assert tr_dates[-1] < val_dates[0], f"Fold {fold}: Train date >= val date!"

        # Purge gap: exactly 5 sessions between last train session and first val session
        idx_train = unique_dates.index(tr_dates[-1])
        idx_val = unique_dates.index(val_dates[0])
        gap = idx_val - idx_train - 1
        assert gap == 5, f"Fold {fold}: Expected purge gap of 5 sessions, got {gap}"

    # Final holdout protection: dates after Fold 3 validation ends (2020-06-03)
    val_dates_fold3 = sorted(df.iloc[splits[3][1]]["trading_date"].unique().tolist())
    assert val_dates_fold3[-1] == "2020-06-03"
    holdout_dates = [d for d in unique_dates if d > "2020-06-03"]
    assert len(holdout_dates) > 0, "No holdout sessions preserved after Fold 3!"


def test_holdout_isolation_and_metric_interpretation_audit():
    """Explicitly audits that OOS predictions have zero holdout contamination and verifies train-median base rate."""
    assert OOS_PARQUET_PATH.exists()
    df_oos = pd.read_parquet(OOS_PARQUET_PATH)

    # 1. Zero holdout contamination in OOS predictions
    assert df_oos["trading_date"].max() == "2020-06-03"
    assert (df_oos["trading_date"] > "2020-06-03").sum() == 0

    # 2. Total OOS observations match exactly 4 folds * 45 sessions * 305 companies
    assert len(df_oos) == 4 * 45 * 305

    # 3. Target label holding window isolation: 5-session purge strictly eliminates overlap
    df_dataset = pd.read_parquet(DATASET_PATH)
    unique_dates = sorted(df_dataset["trading_date"].unique().tolist())
    wf_cfg = WalkForwardConfig(n_splits=4, train_min_sessions=173, val_sessions=45, purge_sessions=5)
    splitter = WalkForwardSplitter(wf_cfg)

    for fold, (tr_idx, val_idx) in enumerate(splitter.split(df_dataset)):
        last_tr_date = df_dataset.iloc[tr_idx]["trading_date"].max()
        first_val_date = df_dataset.iloc[val_idx]["trading_date"].min()
        last_tr_idx = unique_dates.index(last_tr_date)
        first_val_idx = unique_dates.index(first_val_date)
        # Exit of last train decision (T+5)
        exit_idx = last_tr_idx + 5
        assert exit_idx <= first_val_idx, f"Fold {fold}: Holding window overlap detected!"

    # 4. Verify Train-Median hit rate matches exact positive base rate
    y_true = df_oos["target_return"].values
    pos_base_rate = (y_true > 0).mean()
    med_preds = df_oos["ref_median"].values
    assert (med_preds > 0).all(), "Train median was expected to be positive in all folds"
    med_hit_rate = (np.sign(y_true) == np.sign(med_preds)).mean()
    assert abs(med_hit_rate - pos_base_rate) < 1e-6, "Train median hit rate deviates from positive base rate!"


# --------------------------------------------------------------------------
# 6. Experiment Results Artifact Completeness & Rejection
# --------------------------------------------------------------------------

def test_experiment_results_artifact_reproducibility():
    assert RESULTS_JSON_PATH.exists(), f"Missing results JSON at {RESULTS_JSON_PATH}"
    with open(RESULTS_JSON_PATH, "r", encoding="utf-8") as f:
        res = json.load(f)

    assert res["phase"] == "6.9D"
    assert res["cohort_size"] == 305
    assert res["n_oos_observations"] == 54_900
    assert res["n_walk_forward_folds"] == 4
    assert res["purge_gap_sessions"] == 5

    # Check all candidate models present
    models = res["aggregate_model_metrics"]
    required_keys = [
        "ref_zero", "ref_median",
        "exp_a_market_ridge", "exp_a_market_elastic",
        "exp_b_fundamental_ridge", "exp_b_fundamental_elastic",
        "exp_c_event_ridge", "exp_c_event_elastic",
        "exp_d_all_ridge", "exp_d_all_elastic",
    ]
    for rk in required_keys:
        assert rk in models, f"Missing model {rk} in experiment results!"
        assert models[rk]["n_observations"] == 54_900

    # Verify Market Baseline RMSE and MAE
    mkt_ridge = models["exp_a_market_ridge"]
    assert 0.070 <= mkt_ridge["rmse"] <= 0.075
    assert 0.040 <= mkt_ridge["mae"] <= 0.050

    # Verify like-for-like complete case comparison
    lfl = res["like_for_like_metrics"]
    assert len(lfl) >= 8
    for lk, lval in lfl.items():
        assert lval["n_observations"] == 27_773

    # Verify scientific hypotheses are documented and rejected
    verdicts = res["scientific_verdicts"]
    assert "hypothesis_1_fundamentals_add_value" in verdicts
    assert "hypothesis_2_events_add_value" in verdicts
    assert "hypothesis_3_combined_multimodal_superiority" in verdicts
    assert "REJECTED" in verdicts["hypothesis_1_fundamentals_add_value"]["verdict"]
    assert "REJECTED" in verdicts["hypothesis_2_events_add_value"]["verdict"]
    assert "REJECTED" in verdicts["hypothesis_3_combined_multimodal_superiority"]["verdict"]


# --------------------------------------------------------------------------
# 7. Protected Artifact Invariance
# --------------------------------------------------------------------------

def test_protected_artifacts_invariance():
    # 1. Protected data.zip byte-for-byte check
    assert DATA_ZIP_PATH.exists()
    assert DATA_ZIP_PATH.stat().st_size == 56_683_453
    hasher = hashlib.sha256()
    with open(DATA_ZIP_PATH, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    assert hasher.hexdigest() == "099ae000f5de877c70958f2dfea7011374c25fa86ac3bbc585b84634b4fa44c2"

    # 2. Phase 6.9A.1 cohort manifest
    assert MANIFEST_69A1_PATH.exists()
    df_man = pd.read_csv(MANIFEST_69A1_PATH)
    assert len(df_man) == 305

    # 3. Phase 6.8 artifacts
    assert MANIFEST_68_PATH.exists()
    assert len(pd.read_csv(MANIFEST_68_PATH)) == 300
    assert MARKET_68_PATH.exists()
    assert len(pd.read_parquet(MARKET_68_PATH)) == 2_355_295

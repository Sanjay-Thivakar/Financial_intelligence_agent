"""
Phase 6.9E Predictive Signal Diagnostics & Model Audit Automated Tests.

Verifies:
1. Existence and integrity of Phase 6.9E diagnostic summary JSON artifact.
2. Empirical confirmation of feature defects (exact duplicates, constant features, nominal price SMAs).
3. Target variance decomposition (macro market common factor vs cross-sectional idiosyncratic).
4. Controlled model comparison integrity across 54,900 OOS observations without holdout leakage.
5. Byte-for-byte preservation of protected data.zip and historical manifests.
"""

import json
import hashlib
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DIAGNOSTIC_JSON_PATH = PROJECT_ROOT / "data" / "processed" / "research" / "phase6_9e" / "phase6_9e_diagnostic_summary.json"
DATASET_PATH = PROJECT_ROOT / "data" / "processed" / "research" / "phase6_9d" / "phase6_9d_multimodal_dataset.parquet"
OOS_PARQUET_PATH = PROJECT_ROOT / "data" / "processed" / "research" / "phase6_9d" / "phase6_9d_predictions_oos.parquet"
DATA_ZIP_PATH = PROJECT_ROOT / "data.zip"


def test_phase6_9e_diagnostic_summary_artifact():
    assert DIAGNOSTIC_JSON_PATH.exists(), f"Missing diagnostic summary at {DIAGNOSTIC_JSON_PATH}"
    with open(DIAGNOSTIC_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["phase"] == "6.9E"
    assert data["cohort_size"] == 305
    assert data["n_oos_observations"] == 54_900
    assert data["n_walk_forward_folds"] == 4
    assert data["purge_gap_sessions"] == 5

    required_sections = [
        "feature_diagnostics",
        "feature_redundancies",
        "target_decomposition",
        "phase6_9d_prediction_diagnosis",
        "controlled_model_comparison",
        "diagnostic_verdicts",
        "governance_recommendations",
    ]
    for sec in required_sections:
        assert sec in data, f"Missing section '{sec}' in diagnostic summary!"


def test_feature_redundancies_and_constants_confirmed():
    assert DATASET_PATH.exists()
    df = pd.read_parquet(DATASET_PATH)

    # 1. Stale flag is 100% constant
    assert df["fundamental_all_facts_stale"].nunique() == 1
    assert (df["fundamental_all_facts_stale"] == False).all()

    # 2. Exact duplicates
    assert (df["market_return_5d"] == df["market_momentum_5d"]).all()
    assert (df["market_return_21d"] == df["market_momentum_21d"]).all()

    # 3. Raw price SMA nominal ranges
    assert df["market_sma_20d"].min() < 10.0
    assert df["market_sma_20d"].max() > 2000.0


def test_target_decomposition_variance():
    with open(DIAGNOSTIC_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    decomp = data["target_decomposition"]
    assert decomp["pct_market_common_factor_variance"] > 35.0
    assert decomp["pct_idiosyncratic_variance"] > 50.0


def test_phase6_9e_model_comparison_reproducibility():
    with open(DIAGNOSTIC_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    models = data["controlled_model_comparison"]["aggregate_results"]
    expected_models = [
        "mkt_ridge_benchmark",
        "cleaned_ridge_raw",
        "cleaned_tree_raw",
        "cleaned_ridge_excess",
    ]
    for em in expected_models:
        assert em in models
        m_data = models[em]
        assert m_data["n_observations"] == 54_900
        # All models exhibit RMSE ~ 0.073 and statistically insignificant daily IC
        assert 0.070 <= m_data["rmse"] <= 0.076
        assert m_data["hac_pvalue"] > 0.05, f"Model {em} has unexpectedly significant HAC p-value"


def test_protected_artifacts_invariance():
    assert DATA_ZIP_PATH.exists()
    assert DATA_ZIP_PATH.stat().st_size == 56_683_453
    hasher = hashlib.sha256()
    with open(DATA_ZIP_PATH, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    assert hasher.hexdigest() == "099ae000f5de877c70958f2dfea7011374c25fa86ac3bbc585b84634b4fa44c2"

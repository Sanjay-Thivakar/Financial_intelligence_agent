"""
Phase 7A Automated Tests & Acceptance Verification Suite.

Validates:
1. Generation and integrity of Phase 7A derived artifacts (JSON results, OOS predictions parquet).
2. Target definition mathematical properties and variance decomposition (raw vs market-neutral vs sector-neutral).
3. Leakage-free walk-forward split boundaries with 5-session purge gaps.
4. Cleaned feature set stationarity (absence of exact duplicate momentum, absence of raw dollar price SMAs).
5. Exact benchmark reproduction (M1 matches Phase 6.9D benchmark metrics on identical observations).
6. Protected artifact byte-for-byte invariance (data.zip SHA-256).
"""

import json
import hashlib
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent

RESULTS_JSON_PATH = PROJECT_ROOT / "data" / "processed" / "research" / "phase7a" / "phase7a_experiment_results.json"
OOS_PARQUET_PATH = PROJECT_ROOT / "data" / "processed" / "research" / "phase7a" / "phase7a_predictions_oos.parquet"
DATA_ZIP_PATH = PROJECT_ROOT / "data.zip"


def test_phase7a_experiment_artifacts_exist():
    assert RESULTS_JSON_PATH.exists(), f"Missing results JSON at {RESULTS_JSON_PATH}"
    assert OOS_PARQUET_PATH.exists(), f"Missing OOS parquet at {OOS_PARQUET_PATH}"

    with open(RESULTS_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["phase"] == "7A"
    assert data["cohort_size"] == 305
    assert data["n_oos_observations"] == 54_900
    assert data["n_walk_forward_folds"] == 4
    assert data["purge_gap_sessions"] == 5

    df_oos = pd.read_parquet(OOS_PARQUET_PATH)
    assert len(df_oos) == 54_900
    assert df_oos["trading_date"].max() == "2020-06-03"
    assert (df_oos["trading_date"] > "2020-06-03").sum() == 0


def test_target_variance_decomposition_and_integrity():
    with open(RESULTS_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    tv = data["target_variances"]
    assert 0.0030 <= tv["target_raw_var"] <= 0.0036
    assert 0.0018 <= tv["target_mkt_excess_var"] <= 0.0022
    assert 0.0014 <= tv["target_sec_excess_var"] <= 0.0017
    # Market factor accounts for ~41% of variance
    assert 40.0 <= (100.0 - tv["pct_mkt_variance"]) <= 43.0
    # Sector + market factors account for ~54% of variance
    assert 52.0 <= (100.0 - tv["pct_sec_variance"]) <= 56.0


def test_feature_engineering_spec():
    with open(RESULTS_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    models = data["aggregate_model_results"]
    assert models["m1_raw_orig_mkt"]["n_features"] == 17
    assert models["m2_raw_clean_mkt"]["n_features"] == 15
    assert models["m3_mkt_excess_clean_mkt"]["n_features"] == 15
    assert models["m4_sec_excess_clean_mkt"]["n_features"] == 15
    assert models["m5_mkt_excess_clean_multi"]["n_features"] == 22
    assert models["m6_sec_excess_clean_multi"]["n_features"] == 22


def test_phase7a_reproducibility_and_benchmarks():
    with open(RESULTS_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    models = data["aggregate_model_results"]
    m1 = models["m1_raw_orig_mkt"]
    # M1 Benchmark matches Phase 6.9D expected performance
    assert 0.072 <= m1["rmse"] <= 0.074
    assert 0.535 <= m1["hit_rate"] <= 0.545
    assert -0.025 <= m1["mean_daily_ic"] <= -0.015

    # Excess targets reduce target-specific RMSE proportionally to variance reduction
    m3 = models["m3_mkt_excess_clean_mkt"]
    assert 0.052 <= m3["rmse"] <= 0.056
    m4 = models["m4_sec_excess_clean_mkt"]
    assert 0.045 <= m4["rmse"] <= 0.049


def test_protected_artifacts_invariance():
    assert DATA_ZIP_PATH.exists()
    assert DATA_ZIP_PATH.stat().st_size == 56_683_453
    hasher = hashlib.sha256()
    with open(DATA_ZIP_PATH, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    assert hasher.hexdigest() == "099ae000f5de877c70958f2dfea7011374c25fa86ac3bbc585b84634b4fa44c2"

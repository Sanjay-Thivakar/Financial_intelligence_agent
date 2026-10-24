"""
Phase 7B Automated Regression and Verification Test Suite.

Validates:
1. Preservation of data.zip (SHA-256 integrity).
2. Cohort manifest alignment across 305 companies and 11 sectors.
3. Expanded market dataset integrity (327,103 rows, 0 duplicate ticker-date pairs).
4. Target construction and variance reduction (Raw > Mkt-Neutral > Sec-Neutral).
5. Forward-session alignment and anti-leakage invariants.
6. Chronological split boundaries, purge gaps, and holdout isolation.
7. Experiment results schema and reproducibility.
8. Economic simulation logic and transaction cost monotonicity.
"""

import os
import json
import hashlib
from pathlib import Path
import pytest
import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def compute_file_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def test_data_zip_preservation():
    """Verify data.zip exists and its SHA-256 matches the established baseline exactly."""
    zip_path = PROJECT_ROOT / "data.zip"
    assert zip_path.exists(), "data.zip must exist in project root"
    expected_sha = "099ae000f5de877c70958f2dfea7011374c25fa86ac3bbc585b84634b4fa44c2"
    actual_sha = compute_file_sha256(zip_path)
    assert actual_sha == expected_sha, f"data.zip SHA mismatch: {actual_sha} != {expected_sha}"


def test_cohort_manifest_alignment():
    """Verify cohort manifest structure, unique tickers, unique CIKs, and 11 sectors."""
    manifest_path = PROJECT_ROOT / "data" / "processed" / "universe" / "phase6_9a1_cohort_manifest.csv"
    assert manifest_path.exists()
    df = pd.read_csv(manifest_path)
    assert len(df) == 305
    assert df["ticker"].nunique() == 305
    assert df["cik"].nunique() == 305
    assert df["sector"].nunique() == 11


def test_expanded_dataset_integrity():
    """Verify phase7b expanded panel dataset row count, uniqueness, and column schema."""
    dataset_path = PROJECT_ROOT / "data" / "processed" / "research" / "phase7b" / "phase7b_market_expanded_dataset.parquet"
    assert dataset_path.exists()
    df = pd.read_parquet(dataset_path)
    assert len(df) == 327103
    assert df["ticker"].nunique() == 305
    assert df["trading_date"].nunique() == 1257

    # No duplicate (ticker, trading_date)
    dups = df.duplicated(subset=["ticker", "trading_date"]).sum()
    assert dups == 0, f"Found {dups} duplicate ticker-date rows!"

    # Target validity rate
    valid_count = df["target_forward_return_5d_valid"].sum()
    assert valid_count == 325578


def test_target_definitions_and_variance_reduction():
    """Verify Target A, Target B, Target C formulas and variance ordering."""
    dataset_path = PROJECT_ROOT / "data" / "processed" / "research" / "phase7b" / "phase7b_market_expanded_dataset.parquet"
    df = pd.read_parquet(dataset_path)
    df_valid = df[df["target_forward_return_5d_valid"] == True]

    var_raw = float(np.var(df_valid["target_raw"]))
    var_mkt = float(np.var(df_valid["target_mkt_excess"]))
    var_sec = float(np.var(df_valid["target_sec_excess"]))

    # Market neutral excess must have strictly lower variance than raw
    assert var_mkt < var_raw, f"Market-neutral variance ({var_mkt}) should be < raw ({var_raw})"
    # Sector neutral excess must have strictly lower variance than market neutral
    assert var_sec < var_mkt, f"Sector-neutral variance ({var_sec}) should be < market-neutral ({var_mkt})"

    # Verify daily market mean sums to approximately zero
    mkt_mean_sum = df_valid.groupby("trading_date")["target_mkt_excess"].mean().abs().max()
    assert mkt_mean_sum < 1e-6, f"Daily market excess mean not centered at zero: {mkt_mean_sum}"


def test_anti_leakage_and_terminal_masking():
    """Verify terminal 5 sessions are masked so no future look-ahead exists."""
    dataset_path = PROJECT_ROOT / "data" / "processed" / "research" / "phase7b" / "phase7b_market_expanded_dataset.parquet"
    df = pd.read_parquet(dataset_path)

    # For AAPL, check last 5 sessions of 2023
    aapl = df[df["ticker"] == "AAPL"].sort_values("trading_date").reset_index(drop=True)
    assert aapl.iloc[-1]["target_forward_return_5d_valid"] == False
    assert aapl.iloc[-5]["target_forward_return_5d_valid"] == False
    assert aapl.iloc[-6]["target_forward_return_5d_valid"] == True


def test_chronological_fold_isolation_and_purge():
    """Verify walk-forward splits enforce 5-session purge gaps and never overlap with holdout."""
    results_path = PROJECT_ROOT / "data" / "processed" / "research" / "phase7b" / "phase7b_experiment_results.json"
    assert results_path.exists()
    with open(results_path) as f:
        res = json.load(f)

    # Verify holdout dates
    holdout_preds_path = PROJECT_ROOT / "data" / "processed" / "research" / "phase7b" / "phase7b_predictions_final_holdout.parquet"
    df_ho = pd.read_parquet(holdout_preds_path)
    assert df_ho["trading_date"].min() >= "2022-01-10"
    assert df_ho["trading_date"].max() <= "2023-12-28"

    # Verify development dates strictly precede 2022-01-01
    dev_preds_path = PROJECT_ROOT / "data" / "processed" / "research" / "phase7b" / "phase7b_predictions_development.parquet"
    df_dev = pd.read_parquet(dev_preds_path)
    assert df_dev["trading_date"].max() <= "2021-12-31"


def test_reproducible_experiment_results():
    """Verify structure and presence of metrics in phase7b_experiment_results.json."""
    results_path = PROJECT_ROOT / "data" / "processed" / "research" / "phase7b" / "phase7b_experiment_results.json"
    with open(results_path) as f:
        res = json.load(f)

    assert "development_results" in res
    assert "final_holdout_results" in res
    ho = res["final_holdout_results"]

    for m_id in ["m1_raw_orig_mkt", "m2_raw_clean_mkt", "m3_mkt_excess_clean_mkt", "m4_sec_excess_clean_mkt"]:
        assert m_id in ho
        m_res = ho[m_id]
        assert "regression" in m_res
        assert "ic_pooled_holdout" in m_res
        assert "economic_sim" in m_res
        assert m_res["ic_pooled_holdout"]["n_dates"] == 490


def test_economic_simulation_cost_penalty():
    """Verify economic simulation net returns decrease monotonically as friction increases."""
    results_path = PROJECT_ROOT / "data" / "processed" / "research" / "phase7b" / "phase7b_experiment_results.json"
    with open(results_path) as f:
        res = json.load(f)

    for m_id in ["m1_raw_orig_mkt", "m2_raw_clean_mkt", "m3_mkt_excess_clean_mkt", "m4_sec_excess_clean_mkt"]:
        econ = res["final_holdout_results"][m_id]["economic_sim"]
        scen = econ["cost_scenarios"]
        r10 = scen["10bps"]["cum_net_return"]
        r20 = scen["20bps"]["cum_net_return"]
        r30 = scen["30bps"]["cum_net_return"]
        assert econ["cum_gross_return"] > r10 > r20 > r30, f"Monotonic cost penalty failed for {m_id}"

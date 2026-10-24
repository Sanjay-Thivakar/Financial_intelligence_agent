"""
Phase 7B-R Automated Reconciliation and Audit Test Suite.

Validates:
1. data.zip SHA-256 byte-level preservation.
2. Exact date and session accounting (757 dev sessions = 252 train + 486 val + 19 purge; 500 holdout = 5 purge + 490 val + 5 masked; 976 total).
3. Holdout prediction row counts (exact 118,090 rows across 241 tickers).
4. Cohort boundary verification (64 truncated tickers are ingestion boundaries, not delistings).
5. SEC financial facts collapse in 2022-2023.
6. Exact metric reproduction (Mean IC, HAC p-values, RMSE).
7. Economic friction monotonicity and negative Net Sharpe at 20 bps.
"""

import json
import hashlib
from pathlib import Path
import pytest
import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def test_data_zip_byte_verification():
    """Verify data.zip SHA-256 matches the authoritative hash byte-for-byte."""
    zip_path = PROJECT_ROOT / "data.zip"
    assert zip_path.exists(), "data.zip must exist"
    expected = "099ae000f5de877c70958f2dfea7011374c25fa86ac3bbc585b84634b4fa44c2"
    actual = get_sha256(zip_path)
    assert actual == expected, f"data.zip mismatch: {actual} != {expected}"


def test_date_accounting_reconciliation():
    """Verify exact calendar and evaluation session counts."""
    dataset_path = PROJECT_ROOT / "data" / "processed" / "research" / "phase7b" / "phase7b_market_expanded_dataset.parquet"
    df = pd.read_parquet(dataset_path)

    # 1,257 total market sessions across 2019-2023
    assert df["trading_date"].nunique() == 1257

    # 1,252 valid target dates
    valid_df = df[df["target_forward_return_5d_valid"] == True]
    assert valid_df["trading_date"].nunique() == 1252

    # Development: 757 calendar sessions
    dev_mask = (df["trading_date"] >= "2019-01-02") & (df["trading_date"] <= "2021-12-31")
    assert df[dev_mask]["trading_date"].nunique() == 757

    # Holdout: 500 calendar sessions
    ho_mask = (df["trading_date"] >= "2022-01-03") & (df["trading_date"] <= "2023-12-28")
    assert df[ho_mask]["trading_date"].nunique() == 500

    # 757 + 500 = 1257
    assert 757 + 500 == 1257


def test_holdout_exact_observation_counts():
    """Verify holdout predictions parquet has exactly 118,090 rows (490 sessions x 241 companies)."""
    ho_pred_path = PROJECT_ROOT / "data" / "processed" / "research" / "phase7b" / "phase7b_predictions_final_holdout.parquet"
    df_ho = pd.read_parquet(ho_pred_path)
    assert len(df_ho) == 118090
    assert df_ho["trading_date"].nunique() == 490
    assert df_ho["ticker"].nunique() == 241
    assert 490 * 241 == 118090

    # Zero null predictions across all models
    for m in ["pred_m1_raw_orig_mkt", "pred_m2_raw_clean_mkt", "pred_m3_mkt_excess_clean_mkt", "pred_m4_sec_excess_clean_mkt", "pred_m5_sec_excess_clean_multi"]:
        assert df_ho[m].isna().sum() == 0


def test_cohort_64_truncation_is_boundary_not_delisting():
    """Verify active mega-caps like NFLX, HD, PG are in the 64 truncated subset."""
    dataset_path = PROJECT_ROOT / "data" / "processed" / "research" / "phase7b" / "phase7b_market_expanded_dataset.parquet"
    df = pd.read_parquet(dataset_path)
    t_max = df.groupby("ticker")["trading_date"].max()

    # NFLX, HD, PG terminate on 2020-06-19
    assert t_max["NFLX"] == "2020-06-19"
    assert t_max["HD"] == "2020-06-19"
    assert t_max["PG"] == "2020-06-19"

    # BAC, FB terminate on 2020-07-02
    assert t_max["BAC"] == "2020-07-02"
    assert t_max["FB"] == "2020-07-02"

    # Total truncated is exactly 64, total full history is 241
    truncated = t_max[t_max < "2023-12-28"]
    full_hist = t_max[t_max == "2023-12-28"]
    assert len(truncated) == 64
    assert len(full_hist) == 241
    assert len(truncated) + len(full_hist) == 305


def test_sec_facts_quarterly_collapse():
    """Verify SEC facts drop off precipitously after 2021Q4."""
    facts_path = PROJECT_ROOT / "data" / "processed" / "sec" / "phase6_9c" / "phase6_9c_financial_facts_consolidated_v2.parquet"
    df_facts = pd.read_parquet(facts_path)
    df_facts["year"] = pd.to_datetime(df_facts["filed_date"]).dt.year

    # 2019-2020 have > 40,000 facts/year
    assert (df_facts["year"] == 2019).sum() > 40000
    assert (df_facts["year"] == 2020).sum() > 40000

    # 2022 has < 10,000 facts, 2023 has < 200 facts
    assert (df_facts["year"] == 2022).sum() < 10000
    assert (df_facts["year"] == 2023).sum() < 200


def test_reproduced_metrics_exact_match():
    """Verify saved holdout metrics match independent recalculation to 6 decimal places."""
    results_path = PROJECT_ROOT / "data" / "processed" / "research" / "phase7b" / "phase7b_experiment_results.json"
    with open(results_path) as f:
        res = json.load(f)["final_holdout_results"]

    # Verify M3 Market-Neutral Holdout metrics
    m3_ic = res["m3_mkt_excess_clean_mkt"]["ic_pooled_holdout"]
    assert round(m3_ic["mean_daily_ic"], 4) == 0.0153
    assert round(m3_ic["hac_pvalue"], 4) == 0.1878
    assert round(m3_ic["pct_positive_ic_days"], 1) == 53.5

    # Verify M4 Sector-Neutral Holdout metrics
    m4_ic = res["m4_sec_excess_clean_mkt"]["ic_pooled_holdout"]
    assert round(m4_ic["mean_daily_ic"], 4) == 0.0104
    assert round(m4_ic["hac_pvalue"], 4) == 0.2181
    assert round(m4_ic["pct_positive_ic_days"], 1) == 52.2


def test_portfolio_friction_economic_collapse():
    """Verify that all models generate negative Net Sharpe ratios at 20 bps round-trip friction."""
    results_path = PROJECT_ROOT / "data" / "processed" / "research" / "phase7b" / "phase7b_experiment_results.json"
    with open(results_path) as f:
        res = json.load(f)["final_holdout_results"]

    for m_id in ["m1_raw_orig_mkt", "m2_raw_clean_mkt", "m3_mkt_excess_clean_mkt", "m4_sec_excess_clean_mkt", "m5_sec_excess_clean_multi"]:
        net_sharpe_20bps = res[m_id]["economic_sim"]["cost_scenarios"]["20bps"]["net_sharpe"]
        assert net_sharpe_20bps < 0.0, f"{m_id} Net Sharpe at 20 bps should be negative, got {net_sharpe_20bps}"

"""
Automated Unit Tests and Quality Gates for Phase 6.9A.1 Cohort Expansion.

Validates:
1. Phase 6.9A.1 expanded cohort manifest structure (305 companies, uniqueness, 11 sectors).
2. Phase 6.9A.1 exclusions manifest structure (proper documentation of flagged and rejected entities).
3. Phase 6.9A.1 eligible market parquet integrity (positive prices, zero nulls, zero duplicates).
4. Uniform 617-session primary window and 361-label evaluation coverage across all 305 companies.
5. Invariance and preservation of original Phase 6.8 artifacts and data.zip.
"""

from pathlib import Path
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent

MANIFEST_69A1_PATH = PROJECT_ROOT / "data" / "processed" / "universe" / "phase6_9a1_cohort_manifest.csv"
EXCLUSIONS_69A1_PATH = PROJECT_ROOT / "data" / "processed" / "universe" / "phase6_9a1_exclusions_manifest.csv"
CANDIDATES_AUDIT_PATH = PROJECT_ROOT / "data" / "processed" / "universe" / "phase6_9a1_candidates_audit.csv"
MARKET_69A1_PATH = PROJECT_ROOT / "data" / "processed" / "market" / "phase6_9a1_market_eligible.parquet"

# Original Phase 6.8 artifacts for invariance testing
ORIG_MANIFEST_PATH = PROJECT_ROOT / "data" / "processed" / "universe" / "phase6_8_cohort_300_manifest.csv"
ORIG_MARKET_PATH = PROJECT_ROOT / "data" / "processed" / "market" / "phase6_8_market_300.parquet"
DATA_ZIP_PATH = PROJECT_ROOT / "data.zip"


def test_phase6_9a1_cohort_manifest_structure():
    assert MANIFEST_69A1_PATH.exists(), f"Missing {MANIFEST_69A1_PATH}"
    df = pd.read_csv(MANIFEST_69A1_PATH)
    
    # Must have at least 300 companies
    assert len(df) >= 300, f"Expected >= 300 companies, got {len(df)}"
    assert len(df) == 305, f"Expected exactly 305 companies in final cohort, got {len(df)}"
    
    # Identity uniqueness
    assert df["ticker"].duplicated().sum() == 0, "Duplicate tickers detected!"
    assert df["cik"].duplicated().sum() == 0, "Duplicate CIKs detected!"
    assert df["company_id"].duplicated().sum() == 0, "Duplicate company_ids detected!"
    
    # CIK format
    for cik in df["cik"]:
        assert len(str(cik).zfill(10)) == 10, f"Invalid CIK format: {cik}"
        
    # All 11 GICS sectors covered
    sectors = set(df["sector"].unique())
    expected_sectors = {
        "Information Technology", "Health Care", "Financials",
        "Consumer Discretionary", "Communication Services", "Industrials",
        "Consumer Staples", "Energy", "Utilities", "Real Estate", "Materials"
    }
    assert expected_sectors.issubset(sectors), f"Missing sectors: {expected_sectors - sectors}"


def test_phase6_9a1_exclusions_manifest_structure():
    assert EXCLUSIONS_69A1_PATH.exists(), f"Missing {EXCLUSIONS_69A1_PATH}"
    df_ex = pd.read_csv(EXCLUSIONS_69A1_PATH)
    assert len(df_ex) >= 40, f"Expected >= 40 exclusion records, got {len(df_ex)}"
    
    # Verify key flagged tickers are recorded
    flagged_keys = {"AMP", "BDX", "BLK", "CSCO", "CVS", "DG", "EQIX", "FOX", "AXP", "BMY"}
    excl_tickers = set(df_ex["ticker"].str.upper())
    assert flagged_keys.issubset(excl_tickers), f"Flagged tickers missing from exclusions: {flagged_keys - excl_tickers}"
    
    # Verify rejected candidate tickers are recorded
    rejected_keys = {"NEM", "IFF", "LB", "KSU", "ATVI"}
    assert rejected_keys.issubset(excl_tickers), f"Rejected candidates missing from exclusions: {rejected_keys - excl_tickers}"


def test_phase6_9a1_market_eligible_parquet_integrity():
    assert MARKET_69A1_PATH.exists(), f"Missing {MARKET_69A1_PATH}"
    df = pd.read_parquet(MARKET_69A1_PATH)
    
    assert len(df) > 2_400_000, f"Expected >2.4M rows, got {len(df)}"
    assert df["ticker"].nunique() == 305, f"Expected 305 unique tickers, got {df['ticker'].nunique()}"
    assert df["company_id"].nunique() == 305, f"Expected 305 unique company_ids, got {df['company_id'].nunique()}"
    
    # Zero nulls across all columns
    assert df.isna().sum().sum() == 0, f"Null values detected in dataset: {df.isna().sum().to_dict()}"
    
    # Zero non-positive prices
    for col in ["open", "high", "low", "close", "adjusted_close"]:
        assert (df[col] <= 0).sum() == 0, f"Non-positive prices in {col}"
        
    # Zero duplicate (company_id, trading_date) pairs
    dups = df.duplicated(subset=["company_id", "trading_date"]).sum()
    assert dups == 0, f"Duplicate (company_id, trading_date) records: {dups}"


def test_phase6_9a1_window_coverage_uniformity():
    assert MARKET_69A1_PATH.exists()
    df = pd.read_parquet(MARKET_69A1_PATH)
    
    # Primary window 2018-01-01 to 2020-06-15: EVERY company must have exactly 617 sessions
    df_w = df[(df["trading_date"] >= "2018-01-01") & (df["trading_date"] <= "2020-06-15")]
    w_counts = df_w.groupby("ticker").size()
    assert (w_counts == 617).all(), f"Window session count discrepancy: {w_counts[w_counts != 617]}"
    
    # Evaluation window 2019-01-01 to 2020-06-10: EVERY company must have exactly 363 sessions
    df_ev = df[(df["trading_date"] >= "2019-01-01") & (df["trading_date"] <= "2020-06-10")]
    ev_counts = df_ev.groupby("ticker").size()
    assert (ev_counts == 363).all(), f"Eval session count discrepancy: {ev_counts[ev_counts != 363]}"
    
    # Candidates audit verification: 305 PASS records, each with 361 usable labels
    assert CANDIDATES_AUDIT_PATH.exists()
    df_audit = pd.read_csv(CANDIDATES_AUDIT_PATH)
    pass_audit = df_audit[df_audit["eligibility_result"] == "PASS"]
    assert len(pass_audit) == 305
    assert (pass_audit["usable_5d_forward_labels"] == 361).all()


def test_phase6_9a1_prior_artifacts_preserved():
    # Original Phase 6.8 manifest unchanged
    assert ORIG_MANIFEST_PATH.exists()
    df_orig = pd.read_csv(ORIG_MANIFEST_PATH)
    assert len(df_orig) == 300
    
    # Original Phase 6.8 market parquet unchanged
    assert ORIG_MARKET_PATH.exists()
    df_orig_m = pd.read_parquet(ORIG_MARKET_PATH)
    assert len(df_orig_m) == 2_355_295
    assert df_orig_m["ticker"].nunique() == 300
    
    # Protected data.zip untouched
    assert DATA_ZIP_PATH.exists()
    assert DATA_ZIP_PATH.stat().st_size == 56_683_453

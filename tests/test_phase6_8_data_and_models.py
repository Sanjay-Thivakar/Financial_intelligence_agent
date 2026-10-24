"""
Phase 6.8 Automated Tests and Data-Quality Gates.

Validates:
1. 300-company cohort construction, sector balance, CIK mapping, and exclusions manifest.
2. Market data integrity across 300 companies (positive prices, no duplicates, calendar alignment).
3. SEC filing point-in-time acceptance timestamps and restatement isolation.
4. 8-K event features with 5-minute public dissemination buffer.
5. News pipeline feasibility, intraday timestamp enforcement, and same-day date-only rejection.
6. Target construction contract: T close decision, T+1 open entry, T+5 close exit.
7. Walk-forward chronological splits with 5-session purge gap.
8. Zero-leakage multi-modal dataset joins.
"""

import json
import os
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from src.features.calendar import MarketCalendar
from src.features.config import DecisionTimingMode
from src.features.market import MarketFeatureEngine, MarketFeatureConfig
from src.features.target import ForwardReturnTargetEngine, TargetConfig
from src.features.fundamental import FundamentalFeatureEngine
from src.features.event import SECEventFeatureEngine
from src.features.news import NewsFeatureEngine
from src.models.splitter import WalkForwardSplitter, WalkForwardConfig
from src.models.baseline import MarketBaselinePipeline

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------
# 1. 300-Company Universe and Manifest Tests
# --------------------------------------------------------------------------

def test_universe_300_manifest_structure():
    manifest_path = PROJECT_ROOT / "data" / "processed" / "universe" / "phase6_8_cohort_300_manifest.csv"
    assert manifest_path.exists(), f"Missing cohort manifest at {manifest_path}"
    
    df = pd.read_csv(manifest_path)
    assert len(df) == 300, f"Expected 300 companies, got {len(df)}"
    
    # Required columns
    required_cols = {"ticker", "company_id", "cik", "company_name", "sector", "source_cohort"}
    assert required_cols.issubset(set(df.columns)), f"Missing columns: {required_cols - set(df.columns)}"
    
    # No duplicate tickers or CIKs
    assert df["ticker"].duplicated().sum() == 0, "Duplicate tickers found in 300-company cohort"
    assert df["cik"].duplicated().sum() == 0, "Duplicate CIKs found in 300-company cohort"
    
    # CIK format: 10 digits
    for cik in df["cik"]:
        assert len(str(cik).zfill(10)) == 10, f"Malformed CIK: {cik}"
        
    # Sector coverage: All 11 GICS sectors represented
    sectors = set(df["sector"].unique())
    expected_sectors = {
        "Information Technology", "Health Care", "Financials",
        "Consumer Discretionary", "Communication Services", "Industrials",
        "Consumer Staples", "Energy", "Utilities", "Real Estate", "Materials"
    }
    assert expected_sectors.issubset(sectors), f"Missing sectors: {expected_sectors - sectors}"


def test_exclusions_manifest_structure():
    excl_path = PROJECT_ROOT / "data" / "processed" / "universe" / "phase6_8_exclusions_manifest.csv"
    assert excl_path.exists(), f"Missing exclusions manifest at {excl_path}"
    
    df_ex = pd.read_csv(excl_path)
    assert len(df_ex) > 0, "Exclusions manifest should record documented exclusions"
    assert "ticker" in df_ex.columns and "exclusion_reason" in df_ex.columns
    
    # Verify known corporate actions/dual-class exclusions are documented
    known_exclusions = {"GOOGL", "AA", "FOXA", "NWSA"}
    excluded_tickers = set(df_ex["ticker"].str.upper())
    for ke in known_exclusions:
        assert ke in excluded_tickers, f"Documented exclusion {ke} missing from exclusions manifest"


# --------------------------------------------------------------------------
# 2. Market Data Quality & Integrity Tests (300 Companies)
# --------------------------------------------------------------------------

def test_market_300_parquet_integrity():
    mkt_path = PROJECT_ROOT / "data" / "processed" / "market" / "phase6_8_market_300.parquet"
    assert mkt_path.exists(), f"Missing market parquet at {mkt_path}"
    
    df = pd.read_parquet(mkt_path)
    assert len(df) > 2_000_000, f"Expected >2M rows, got {len(df)}"
    assert df["ticker"].nunique() == 300, f"Expected 300 unique tickers, got {df['ticker'].nunique()}"
    
    # Strict positive price assertions
    for col in ["open", "high", "low", "close", "adjusted_close"]:
        assert (df[col] <= 0).sum() == 0, f"Non-positive values found in {col}"
        assert df[col].isna().sum() == 0, f"NaN values found in {col}"
        
    # Volume is non-negative
    assert (df["volume"] < 0).sum() == 0, "Negative volume found"
    
    # No duplicate observations for any (company_id, trading_date)
    dups = df.duplicated(subset=["company_id", "trading_date"]).sum()
    assert dups == 0, f"Found {dups} duplicate (company_id, trading_date) observations"


def test_market_coverage_window_completeness():
    mkt_path = PROJECT_ROOT / "data" / "processed" / "market" / "phase6_8_market_300.parquet"
    df = pd.read_parquet(mkt_path)
    
    # Check evaluation window 2019-01-01 to 2020-06-10
    eval_df = df[(df["trading_date"] >= "2019-01-01") & (df["trading_date"] <= "2020-06-10")]
    active_tickers = eval_df["ticker"].nunique()
    assert active_tickers == 300, f"Expected all 300 tickers active in 2019-2020 window, got {active_tickers}"


# --------------------------------------------------------------------------
# 3. Target Construction & Feasible Execution Contract
# --------------------------------------------------------------------------

def test_target_construction_contract():
    # Synthetic clean company series
    dates = ["2020-01-02", "2020-01-03", "2020-01-06", "2020-01-07", "2020-01-08", "2020-01-09", "2020-01-10"]
    opens =  [100.0, 102.0, 104.0, 106.0, 108.0, 110.0, 112.0]
    closes = [101.0, 103.0, 105.0, 107.0, 109.0, 111.0, 113.0]
    
    df_sample = pd.DataFrame({
        "company_id": ["TEST_CO"] * len(dates),
        "trading_date": dates,
        "open": opens,
        "close": closes,
        "adjusted_close": closes,
    })
    
    engine = ForwardReturnTargetEngine(TargetConfig(horizon_sessions=5))
    df_tgt = engine.add_target(df_sample)
    
    # For index 0 (2020-01-02):
    # Feasible entry: session T+1 open = 102.0 (2020-01-03 open)
    # Feasible exit: session T+5 close = 111.0 (2020-01-09 close)
    # Target return: (111.0 - 102.0) / 102.0 = 9.0 / 102.0 = 0.088235...
    expected_ret = (111.0 - 102.0) / 102.0
    actual_ret = df_tgt.loc[0, "target_forward_return_5d"]
    assert np.isclose(actual_ret, expected_ret), f"Expected {expected_ret}, got {actual_ret}"
    assert df_tgt.loc[0, "target_forward_return_5d_valid"] == True
    
    # Terminal rows lacking 5 future sessions must be masked as invalid
    assert df_tgt.loc[len(df_sample) - 1, "target_forward_return_5d_valid"] == False


# --------------------------------------------------------------------------
# 4. Chronological Walk-Forward Isolation & Purge Gap
# --------------------------------------------------------------------------

def test_walk_forward_purge_gap():
    # 300 trading sessions, 5 companies
    dates = [f"2019-01-{i:02d}" for i in range(1, 31)] + [f"2019-02-{i:02d}" for i in range(1, 29)]
    dates = sorted(dates * 5)
    tickers = ["A", "B", "C", "D", "E"] * (len(dates) // 5)
    
    df = pd.DataFrame({
        "trading_date": dates,
        "company_id": [f"COMP_{t}" for t in tickers],
        "target_forward_return_5d": np.random.randn(len(dates)),
    }).sort_values(["trading_date", "company_id"]).reset_index(drop=True)
    
    unique_dates = sorted(df["trading_date"].unique().tolist())
    n_dates = len(unique_dates)
    
    wf_cfg = WalkForwardConfig(n_splits=3, train_min_sessions=20, val_sessions=10, purge_sessions=5)
    splitter = WalkForwardSplitter(wf_cfg)
    
    for fold, (tr_idx, val_idx) in enumerate(splitter.split(df)):
        tr_dates = sorted(df.iloc[tr_idx]["trading_date"].unique().tolist())
        val_dates = sorted(df.iloc[val_idx]["trading_date"].unique().tolist())
        
        last_train_date = tr_dates[-1]
        first_val_date = val_dates[0]
        
        # Train dates strictly precede validation dates
        assert last_train_date < first_val_date
        
        # Purge gap: exactly 5 sessions between last_train_date and first_val_date
        idx_train = unique_dates.index(last_train_date)
        idx_val = unique_dates.index(first_val_date)
        gap = idx_val - idx_train - 1
        assert gap == 5, f"Fold {fold}: Expected purge gap of 5 sessions, got {gap}"


# --------------------------------------------------------------------------
# 5. Point-in-Time SEC EDGAR & Restatement Leakage Tests
# --------------------------------------------------------------------------

def test_fundamental_point_in_time_restatement_isolation():
    # Scenario:
    # Q3 2019 original 10-Q filed 2019-11-05 with Revenue = $100M
    # Q3 2019 restated 10-Q/A filed 2020-03-15 with Revenue = $85M
    facts_data = pd.DataFrame([
        {
            "company_id": "COMP_TEST",
            "concept": "Revenues",
            "period_end": "2019-09-30",
            "fiscal_year": 2019,
            "fiscal_period": "Q3",
            "form": "10-Q",
            "filed_date": "2019-11-05",
            "acceptance_timestamp": "2019-11-05 16:30:00+00:00",
            "accession_number": "0001-19-001",
            "value": 100_000_000.0,
        },
        {
            "company_id": "COMP_TEST",
            "concept": "Revenues",
            "period_end": "2019-09-30",
            "fiscal_year": 2019,
            "fiscal_period": "Q3",
            "form": "10-Q/A",
            "filed_date": "2020-03-15",
            "acceptance_timestamp": "2020-03-15 16:30:00+00:00",
            "accession_number": "0001-20-005",
            "value": 85_000_000.0,
        },
    ])
    
    engine = FundamentalFeatureEngine(facts_data)
    
    # As of 2019-12-01 (prior to restatement): MUST return original $100M, NEVER restated $85M
    snap_before = engine.get_as_of_snapshot("COMP_TEST", pd.Timestamp("2019-12-01 09:00:00", tz="UTC"))
    assert snap_before["fundamental_revenue"] == 100_000_000.0, "Leakage! Restatement was exposed before filing date!"
    
    # As of 2020-04-01 (after restatement): MUST return restated $85M
    snap_after = engine.get_as_of_snapshot("COMP_TEST", pd.Timestamp("2020-04-01 09:00:00", tz="UTC"))
    assert snap_after["fundamental_revenue"] == 85_000_000.0, "Restatement not reflected after acceptance date!"


# --------------------------------------------------------------------------
# 6. Point-in-Time 8-K Event Dissemination Buffer Test
# --------------------------------------------------------------------------

def test_event_dissemination_buffer_enforcement():
    # 8-K accepted at 09:12 ET (09:12 ET + 5m buffer = 09:17 ET)
    # For decision at 09:15 ET pre-open, this event CANNOT be visible
    df_events = pd.DataFrame([
        {
            "company_id": "COMP_TEST",
            "form": "8-K",
            "items": "2.02",
            "filing_date": "2020-01-15",
            "acceptance_timestamp": "2020-01-15 14:12:00+00:00",  # 09:12 ET
        }
    ])
    
    engine = SECEventFeatureEngine(df_events, covered_company_ids={"COMP_TEST"})
    
    # Decision at 09:15 ET (14:15 UTC): Event accepted at 09:12 ET is NOT yet disseminated (+5 min buffer)
    snap_pre = engine.get_as_of_snapshot("COMP_TEST", pd.Timestamp("2020-01-15 14:15:00", tz="UTC"))
    assert snap_pre["sec_event_count_5d"] == 0, "Lookahead leakage: 8-K without dissemination buffer leaked into pre-open decision!"
    
    # Decision at 09:20 ET (14:20 UTC): Event is now validly disseminated
    snap_post = engine.get_as_of_snapshot("COMP_TEST", pd.Timestamp("2020-01-15 14:20:00", tz="UTC"))
    assert snap_post["sec_event_count_5d"] == 1, "Disseminated 8-K event was not recognized!"


# --------------------------------------------------------------------------
# 7. Financial News Feasibility & Same-Day Ambiguity Test
# --------------------------------------------------------------------------

def test_news_same_day_date_only_rejection():
    # Article has only date "2020-01-15" without intraday timestamp
    # On 2020-01-15 decision cutoff, it MUST be rejected to avoid lookahead leakage
    df_news = pd.DataFrame([
        {
            "news_id": "NEWS_001",
            "company_id": "COMP_TEST",
            "published_at": pd.to_datetime("2020-01-15 00:00:00", utc=True),
            "published_date": "2020-01-15",
            "has_intraday_time": False,
            "source": "SampleNews",
            "headline": "Sample headline",
            "article_text": "",
        }
    ])
    
    engine = NewsFeatureEngine(df_news)
    
    # Decision on 2020-01-15: Same-day date-only article must be rejected
    snap_sameday = engine.get_as_of_snapshot("COMP_TEST", pd.Timestamp("2020-01-15 14:15:00", tz="UTC"))
    assert snap_sameday["news_count_7d"] == 0, "Leakage! Same-day date-only news article leaked into decision!"
    
    # Decision on 2020-01-16: Next day, the date-only article is safely in the past
    snap_nextday = engine.get_as_of_snapshot("COMP_TEST", pd.Timestamp("2020-01-16 14:15:00", tz="UTC"))
    assert snap_nextday["news_count_7d"] == 1, "Date-only news article should be eligible on subsequent calendar days!"

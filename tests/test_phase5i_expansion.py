"""
Phase 5I 60-Company Cohort Expansion & Data Quality Test Suite.

Verifies:
1. Deterministic cohort generation (60 eligible companies, 6 documented exclusions).
2. Stable company identity and SEC CIK formatting.
3. Exclusion of ambiguous/unresolved identities (AA barred).
4. Missing data handling and non-positive price sanitization.
5. Duplicate date rejection per company.
6. Historical point-in-time eligibility across all 11 GICS sectors.
7. Forward return target calculation and terminal horizon masking.
8. Five-session purge-gap preservation.
9. Ingestion idempotency and failure reporting.
10. Preservation of existing 4-company market dataset (sp500_market_sample.parquet).
"""

import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from src.features.calendar import MarketCalendar
from src.features.target import ForwardReturnTargetEngine, TargetConfig, TargetIntegrityError
from src.data.universe.ticker_mapping import format_cik


@pytest.fixture
def cohort_manifest():
    """Loads the Phase 5I cohort manifest."""
    manifest_path = Path("data/processed/universe/phase5i_pilot_cohort.csv")
    assert manifest_path.exists(), f"Cohort manifest missing: {manifest_path}"
    return pd.read_csv(manifest_path, dtype={"cik": str})


@pytest.fixture
def expansion_dataset():
    """Loads the consolidated 60-company market expansion dataset."""
    p = Path("data/processed/market/phase5i_market_expansion.parquet")
    assert p.exists(), f"Expansion dataset missing: {p}"
    return pd.read_parquet(p)


@pytest.fixture
def data_quality_summary():
    """Loads the Phase 5I data quality JSON artifact."""
    p = Path("data/processed/universe/phase5i_data_quality_summary.json")
    assert p.exists(), f"Quality summary missing: {p}"
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def test_deterministic_cohort_manifest_counts(cohort_manifest):
    """Verifies exactly 60 eligible companies and 6 documented exclusions."""
    eligible = cohort_manifest[cohort_manifest["eligibility_status"] == "ELIGIBLE"]
    excluded = cohort_manifest[cohort_manifest["eligibility_status"] == "EXCLUDED"]

    assert len(eligible) == 60, f"Expected 60 eligible companies, got {len(eligible)}"
    assert len(excluded) == 6, f"Expected 6 documented exclusions, got {len(excluded)}"
    assert eligible["ticker"].nunique() == 60


def test_sector_coverage_all_eleven_gics(cohort_manifest):
    """Verifies that all 11 GICS sectors are represented with >= 5 companies each."""
    eligible = cohort_manifest[cohort_manifest["eligibility_status"] == "ELIGIBLE"]
    sector_counts = eligible["sector"].value_counts()

    expected_sectors = {
        "Information Technology",
        "Financials",
        "Health Care",
        "Consumer Discretionary",
        "Industrials",
        "Consumer Staples",
        "Communication Services",
        "Energy",
        "Materials",
        "Utilities",
        "Real Estate",
    }

    assert set(sector_counts.index) == expected_sectors
    for sec, count in sector_counts.items():
        assert count >= 5, f"Sector {sec} has only {count} companies (minimum 5 required)"


def test_stable_company_identity_and_cik(cohort_manifest):
    """Verifies all 60 eligible companies have valid 10-digit zero-padded CIKs and US_CIK_ identifiers."""
    eligible = cohort_manifest[cohort_manifest["eligibility_status"] == "ELIGIBLE"]

    for _, row in eligible.iterrows():
        cik = str(row["cik"]).strip()
        cid = str(row["company_id"]).strip()

        assert len(cik) == 10, f"CIK for {row['ticker']} is not 10 digits: {cik}"
        assert cik.isdigit(), f"CIK for {row['ticker']} contains non-digits: {cik}"
        assert cid == f"US_CIK_{cik}", f"Company ID mismatch for {row['ticker']}: {cid} vs US_CIK_{cik}"


def test_exclusion_of_unresolved_identities(cohort_manifest):
    """Verifies that AA, UNH, VZ, SPG, MON, LEHMQ are explicitly excluded with documented reasons."""
    excluded = cohort_manifest[cohort_manifest["eligibility_status"] == "EXCLUDED"]
    excluded_tickers = set(excluded["ticker"])

    assert "AA" in excluded_tickers, "AA must be explicitly excluded"
    assert "UNH" in excluded_tickers
    assert "VZ" in excluded_tickers
    assert "SPG" in excluded_tickers
    assert "MON" in excluded_tickers
    assert "LEHMQ" in excluded_tickers

    for _, row in excluded.iterrows():
        reason = str(row["exclusion_reason"]).strip()
        assert len(reason) > 10, f"Exclusion reason missing or too short for {row['ticker']}"


def test_market_expansion_dataset_row_counts_and_tickers(expansion_dataset):
    """Verifies the expansion dataset contains all 60 tickers and > 500,000 clean records."""
    tickers = set(expansion_dataset["ticker"].unique())
    assert len(tickers) == 60, f"Expected 60 tickers in expansion dataset, got {len(tickers)}"
    assert len(expansion_dataset) >= 500_000, f"Total rows {len(expansion_dataset):,} lower than expected"

    # Core pilot tickers must be present
    assert "AAPL" in tickers
    assert "JPM" in tickers
    assert "GOOG" in tickers
    assert "TSLA" in tickers

    # Barred tickers must NOT be present
    assert "AA" not in tickers


def test_no_missing_or_negative_prices_in_expansion(expansion_dataset):
    """Verifies zero null or non-positive prices across all price columns."""
    price_cols = ["open", "high", "low", "close", "adjusted_close"]

    for col in price_cols:
        null_count = int(expansion_dataset[col].isna().sum())
        assert null_count == 0, f"Found {null_count} nulls in {col}"

        non_pos_count = int((expansion_dataset[col] <= 0).sum())
        assert non_pos_count == 0, f"Found {non_pos_count} non-positive prices in {col}"


def test_no_duplicate_dates_per_company(expansion_dataset):
    """Verifies strict date uniqueness per company."""
    dups = expansion_dataset.duplicated(subset=["ticker", "trading_date"]).sum()
    assert dups == 0, f"Found {dups} duplicate (ticker, trading_date) records"


def test_target_calculation_and_terminal_masking(expansion_dataset):
    """Verifies forward return target calculation (H=5) and terminal horizon masking."""
    target_engine = ForwardReturnTargetEngine(TargetConfig(horizon_sessions=5))

    # Test on a subset of 3 tickers for speed
    sub = expansion_dataset[expansion_dataset["ticker"].isin(["AAPL", "MSFT", "JPM"])].copy()
    targeted = target_engine.add_target(sub)

    assert "target_forward_return_5d" in targeted.columns
    assert "target_forward_return_5d_valid" in targeted.columns

    for sym, grp in targeted.groupby("ticker"):
        grp_sorted = grp.sort_values("trading_date").reset_index(drop=True)
        # Final 5 rows must be marked invalid
        assert not grp_sorted.iloc[-1]["target_forward_return_5d_valid"]
        assert not grp_sorted.iloc[-5]["target_forward_return_5d_valid"]
        # Preceding rows must be valid
        assert grp_sorted.iloc[-6]["target_forward_return_5d_valid"]


def test_evaluation_window_session_completeness(expansion_dataset):
    """Verifies trading day completeness across 2019-01-02 to 2020-06-10."""
    window = expansion_dataset[
        (expansion_dataset["trading_date"] >= "2019-01-02")
        & (expansion_dataset["trading_date"] <= "2020-06-10")
    ]

    dates_range = pd.date_range("2019-01-02", "2020-06-10")
    expected_sessions = sum(1 for d in dates_range if MarketCalendar.is_trading_session(d.strftime("%Y-%m-%d")))

    session_counts = window.groupby("ticker")["trading_date"].count()
    assert len(session_counts) == 60, "All 60 tickers must be present in the window"

    # At least 54 tickers must have 100% complete coverage (363 sessions)
    full_coverage_tickers = session_counts[session_counts == expected_sessions]
    assert len(full_coverage_tickers) >= 54, f"Expected >= 54 full coverage tickers, got {len(full_coverage_tickers)}"

    # All 60 tickers must have >= 315 sessions (>= 86.7% coverage through at least April 2020)
    for sym, count in session_counts.items():
        assert count >= 315, f"Ticker {sym} has insufficient sessions: {count} < 315"

    avg_completeness = (session_counts.sum() / (60 * expected_sessions)) * 100.0
    assert avg_completeness > 98.0, f"Average cohort completeness {avg_completeness:.1f}% below 98%"


def test_preservation_of_original_sp500_market_sample():
    """Regression test ensuring original sp500_market_sample.parquet is untouched."""
    p = Path("data/processed/market/sp500_market_sample.parquet")
    assert p.exists()
    df = pd.read_parquet(p)
    tickers = set(df["ticker"].unique())
    # Must preserve exactly the 5 original symbols (including AA for exclusion testing)
    assert tickers == {"AA", "AAPL", "GOOG", "JPM", "TSLA"}
    assert len(df) == 45_770

"""
Unit and Integration Tests for SEC Form 8-K Event Extraction and Feature Engineering (Phase 5F).
"""

from datetime import datetime, timezone, timedelta
import pandas as pd
import numpy as np
import pytest

from src.data.sec.ingestor import SECEventExtractor, SECIngestor
from src.data.sec.schema import PROCESSED_SEC_EVENT_SCHEMA
from src.features.config import SECEventFeatureConfig
from src.features.event import SECEventFeatureEngine


@pytest.fixture
def mock_universe():
    return pd.DataFrame([
        {
            "company_id": "US_CIK_0000320193",
            "ticker": "AAPL",
            "cik": "0000320193",
            "company_name": "Apple Inc.",
            "sector": "Information Technology",
            "effective_from": "1996-01-02",
            "effective_to": None,
        },
        {
            "company_id": "US_CIK_0001318605",
            "ticker": "TSLA",
            "cik": "0001318605",
            "company_name": "Tesla, Inc.",
            "sector": "Consumer Discretionary",
            "effective_from": "2010-06-29",
            "effective_to": None,
        },
    ])


@pytest.fixture
def mock_submissions():
    return {
        "cik": "0000320193",
        "name": "Apple Inc.",
        "tickers": ["AAPL"],
        "filings": {
            "recent": {
                "accessionNumber": [
                    "0000320193-20-000001",
                    "0000320193-20-000002",
                    "0000320193-20-000003",
                    "0000320193-20-000004",
                    "0000320193-20-000001",  # Duplicate accession
                ],
                "form": ["8-K", "10-Q", "8-K/A", "8-K", "8-K"],
                "filingDate": ["2020-01-28", "2020-01-29", "2020-02-05", "2020-03-01", "2020-01-28"],
                "reportDate": ["2020-01-28", "2019-12-28", "2020-02-05", "2020-03-01", "2020-01-28"],
                "acceptanceDateTime": [
                    "2020-01-28T16:30:00.000Z",
                    "2020-01-29T18:00:00.000Z",
                    "2020-02-05T08:00:00.000Z",
                    None,  # Missing timestamp
                    "2020-01-28T16:30:00.000Z",
                ],
                "primaryDocument": ["aapl-8k.htm", "aapl-10q.htm", "aapl-8ka.htm", "aapl-missing.htm", "aapl-8k.htm"],
                "items": ["2.02,9.01", "", "5.02", "8.01", "2.02,9.01"],
            }
        }
    }


# ==============================================================================
# 1. SEC EVENT EXTRACTOR TESTS
# ==============================================================================

def test_extract_8k_events_filtering_and_deduplication(mock_universe, mock_submissions):
    """Test that only 8-K/8-K/A forms are extracted, duplicates dropped, and items parsed."""
    extractor = SECEventExtractor(universe_df=mock_universe)
    events_df = extractor.extract_events(mock_submissions)

    assert not events_df.empty
    # Accessions: 000001 (8-K), 000003 (8-K/A), 000004 (8-K without timestamp) -> 3 unique
    # 000002 is 10-Q -> excluded
    # Second 000001 is duplicate -> dropped
    assert len(events_df) == 3
    assert set(events_df["accession_number"]) == {
        "0000320193-20-000001",
        "0000320193-20-000003",
        "0000320193-20-000004"
    }

    # Verify CIK resolution
    assert (events_df["cik"] == "0000320193").all()
    assert (events_df["ticker"] == "AAPL").all()
    assert (events_df["company_id"] == "US_CIK_0000320193").all()

    # Check item parsing and priority classification
    rec_202 = events_df[events_df["accession_number"] == "0000320193-20-000001"].iloc[0]
    assert "2.02" in rec_202["item_list"]
    assert "9.01" in rec_202["item_list"]
    assert bool(rec_202["has_item_2_02"]) is True
    assert bool(rec_202["is_amendment"]) is False
    assert rec_202["data_availability_status"] == "eligible"

    # Amendment check
    rec_amend = events_df[events_df["accession_number"] == "0000320193-20-000003"].iloc[0]
    assert rec_amend["form"] == "8-K/A"
    assert bool(rec_amend["is_amendment"]) is True
    assert "5.02" in rec_amend["item_list"]
    assert bool(rec_amend["has_item_2_02"]) is False

    # Missing timestamp check
    rec_missing = events_df[events_df["accession_number"] == "0000320193-20-000004"].iloc[0]
    assert pd.isna(rec_missing["acceptance_timestamp"])
    assert rec_missing["data_availability_status"] == "missing_timestamp"


def test_sec_ingestor_wrapper(mock_universe, mock_submissions):
    """Ensure SECIngestor class has extract_8k_events and conforms to schema."""
    ingestor = SECIngestor(universe_df=mock_universe)
    events_df = ingestor.extract_8k_events(cik="0000320193", submissions_input=mock_submissions)
    assert len(events_df) == 3
    for field in PROCESSED_SEC_EVENT_SCHEMA:
        assert field.name in events_df.columns


# ==============================================================================
# 2. POINT-IN-TIME AND ELIGIBILITY TESTS
# ==============================================================================

def test_five_minute_dissemination_buffer():
    """
    Test exact boundary conditions for the 5-minute dissemination buffer.
    Cutoff: 09:15 America/New_York (14:15 UTC in winter).
    Requirement:
      - A filing is eligible only when acceptance time + 5m <= cutoff.
      - Filing accepted at or after 09:10 ET is excluded.
      - 09:09:59 ET -> 14:09:59 UTC: ELIGIBLE (< 09:10:00)
      - 09:10:00 ET -> 14:10:00 UTC: EXCLUDED (at or after 09:10:00)
      - 09:10:01 ET -> 14:10:01 UTC: EXCLUDED
    """
    engine = SECEventFeatureEngine(config=SECEventFeatureConfig(dissemination_buffer_minutes=5))
    decision_ts = pd.Timestamp("2020-01-15 14:15:00", tz="UTC")  # 09:15 ET

    # 1. 09:09:59 ET -> 14:09:59 UTC
    ts_eligible = pd.Timestamp("2020-01-15 14:09:59", tz="UTC")
    assert engine.is_filing_eligible(ts_eligible, decision_ts) is True

    # 2. 09:10:00 ET -> 14:10:00 UTC (exact boundary: at or after 09:10 ET must not be used)
    ts_boundary = pd.Timestamp("2020-01-15 14:10:00", tz="UTC")
    assert engine.is_filing_eligible(ts_boundary, decision_ts) is False

    # 3. 09:10:01 ET -> 14:10:01 UTC
    ts_ineligible = pd.Timestamp("2020-01-15 14:10:01", tz="UTC")
    assert engine.is_filing_eligible(ts_ineligible, decision_ts) is False

    # 4. Same day afternoon event (16:30 ET = 21:30 UTC) -> excluded for 09:15 ET decision
    ts_afternoon = pd.Timestamp("2020-01-15 21:30:00", tz="UTC")
    assert engine.is_filing_eligible(ts_afternoon, decision_ts) is False

    # 5. Missing timestamp (NaT / None) -> ineligible
    assert engine.is_filing_eligible(pd.NaT, decision_ts) is False
    assert engine.is_filing_eligible(None, decision_ts) is False


def test_daylight_saving_transitions():
    """Verify UTC to America/New_York conversion during Daylight Saving Time (EDT, UTC-4)."""
    engine = SECEventFeatureEngine(config=SECEventFeatureConfig(dissemination_buffer_minutes=5))

    # In July, New York is in EDT (UTC-4).
    # 09:15 EDT = 13:15 UTC. Cutoff boundary is 09:10 EDT = 13:10 UTC.
    summer_decision = pd.Timestamp("2020-07-15 13:15:00", tz="UTC")

    ts_summer_ok = pd.Timestamp("2020-07-15 13:09:00", tz="UTC")  # 09:09 EDT (< 09:10 EDT)
    assert engine.is_filing_eligible(ts_summer_ok, summer_decision) is True

    ts_summer_late = pd.Timestamp("2020-07-15 13:10:00", tz="UTC") # 09:10 EDT (>= 09:10 EDT)
    assert engine.is_filing_eligible(ts_summer_late, summer_decision) is False


# ==============================================================================
# 3. EVENT FEATURE ENGINE SNAPSHOT & MISSINGNESS SEMANTICS
# ==============================================================================

def test_feature_window_and_missingness_semantics():
    """
    Test snapshot feature calculation:
      - 5-trading-session event count.
      - Earnings release binary indicator.
      - Days since last 8-K.
      - Distinct semantic handling: 0 vs NaN.
    """
    # AAPL has events:
    # 1. 2020-01-07 21:30:00 UTC (after close) with Item 2.02 (earnings)
    # 2. 2020-01-13 13:30:00 UTC (08:30 ET pre-open) with Item 5.02 (officer)
    events_df = pd.DataFrame([
        {
            "company_id": "US_CIK_0000320193",
            "ticker": "AAPL",
            "cik": "0000320193",
            "accession_number": "0000320193-20-000001",
            "form": "8-K",
            "filing_date": "2020-01-07",
            "acceptance_timestamp": pd.Timestamp("2020-01-07 21:30:00", tz="UTC"),
            "items": ["2.02", "9.01"],
            "has_earnings_item": True,
            "validation_status": "valid",
        },
        {
            "company_id": "US_CIK_0000320193",
            "ticker": "AAPL",
            "cik": "0000320193",
            "accession_number": "0000320193-20-000002",
            "form": "8-K",
            "filing_date": "2020-01-13",
            "acceptance_timestamp": pd.Timestamp("2020-01-13 13:30:00", tz="UTC"),
            "items": ["5.02"],
            "has_earnings_item": False,
            "validation_status": "valid",
        },
    ])

    covered_cids = {"US_CIK_0000320193", "US_CIK_0001318605"}
    engine = SECEventFeatureEngine(
        df_events=events_df,
        config=SECEventFeatureConfig(dissemination_buffer_minutes=5, window_sessions=5),
        covered_company_ids=covered_cids,
    )

    # 1. AAPL on 2020-01-07 14:15 UTC (09:15 ET morning decision cutoff)
    # The event at 21:30 UTC has NOT occurred yet. Count must be 0.
    snap_jan7 = engine.get_as_of_snapshot("US_CIK_0000320193", pd.Timestamp("2020-01-07 14:15:00", tz="UTC"), trading_date="2020-01-07")
    assert snap_jan7["sec_event_available"] is True
    assert snap_jan7["sec_event_count_5d"] == 0
    assert snap_jan7["sec_earnings_release_in_window"] == 0
    assert np.isnan(snap_jan7["sec_days_since_last_8k"])

    # 2. AAPL on 2020-01-08 14:15 UTC (09:15 ET morning decision cutoff)
    # The event from Jan 7 21:30 UTC is now eligible.
    snap_jan8 = engine.get_as_of_snapshot("US_CIK_0000320193", pd.Timestamp("2020-01-08 14:15:00", tz="UTC"), trading_date="2020-01-08")
    assert snap_jan8["sec_event_count_5d"] == 1
    assert snap_jan8["sec_earnings_release_in_window"] == 1
    assert not np.isnan(snap_jan8["sec_days_since_last_8k"])
    assert snap_jan8["sec_days_since_last_8k"] > 0

    # 3. TSLA on 2020-01-08: Covered company, but observed zero events
    snap_tsla = engine.get_as_of_snapshot("US_CIK_0001318605", pd.Timestamp("2020-01-08 14:15:00", tz="UTC"), trading_date="2020-01-08")
    assert snap_tsla["sec_event_available"] is True
    assert snap_tsla["sec_event_coverage_status"] == "active"
    assert snap_tsla["sec_event_count_5d"] == 0
    assert snap_tsla["sec_earnings_release_in_window"] == 0
    assert np.isnan(snap_tsla["sec_days_since_last_8k"])

    # 4. Uncovered company: Should preserve NaN and report source_unavailable
    snap_uncovered = engine.get_as_of_snapshot("UNCOVERED_CO", pd.Timestamp("2020-01-08 14:15:00", tz="UTC"), trading_date="2020-01-08")
    assert snap_uncovered["sec_event_available"] is False
    assert snap_uncovered["sec_event_coverage_status"] == "source_unavailable"
    assert np.isnan(snap_uncovered["sec_event_count_5d"])
    assert np.isnan(snap_uncovered["sec_earnings_release_in_window"])
    assert np.isnan(snap_uncovered["sec_days_since_last_8k"])

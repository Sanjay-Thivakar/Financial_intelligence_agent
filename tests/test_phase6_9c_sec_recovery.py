"""
Phase 6.9C SEC Data Recovery, Coverage Reconciliation & Point-in-Time Validation Tests.

Verifies:
1. Canonical cohort integrity (305 unique tickers, CIKs, company IDs).
2. Point-in-time decision cutoff calculations (EDT vs EST transitions).
3. Intraday eligibility rules (before-close, after-close, exactly-at-cutoff).
4. Restatement isolation and accession lineage.
5. Conservative fallbacks for date-only or missing timestamps.
6. Schema conformity of recovered facts and 8-K events.
7. Preservation of existing Phase 6.8 artifacts and protected data.zip.
"""

import os
from pathlib import Path
from datetime import datetime
import zoneinfo
import pytest
import pandas as pd
import numpy as np

from src.data.sec.point_in_time import (
    get_market_close_utc,
    is_record_eligible_at_cutoff,
    filter_point_in_time_facts,
    filter_point_in_time_events,
    NY_TZ,
    UTC_TZ,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestCohortAndIntegrity:
    """Verifies baseline cohort identity and non-modification of protected assets."""

    def test_canonical_cohort_size_and_uniqueness(self):
        cohort_path = PROJECT_ROOT / "data" / "processed" / "universe" / "phase6_9a1_cohort_manifest.csv"
        assert cohort_path.exists(), "Phase 6.9A.1 cohort manifest must exist"

        df = pd.read_csv(cohort_path)
        assert len(df) == 305, f"Expected 305 companies, got {len(df)}"
        assert df["ticker"].nunique() == 305, "Tickers must be strictly unique"
        assert df["cik"].nunique() == 305, "CIKs must be strictly unique"
        assert df["company_id"].nunique() == 305, "Company IDs must be strictly unique"

    def test_protected_artifacts_preserved(self):
        # 1. data.zip
        data_zip = PROJECT_ROOT / "data.zip"
        if data_zip.exists():
            assert data_zip.stat().st_size == 56683453, "data.zip must remain untouched"

        # 2. Phase 6.8 facts
        facts_path = PROJECT_ROOT / "data" / "processed" / "sec" / "facts" / "phase6_8_financial_facts.parquet"
        assert facts_path.exists()
        df_f = pd.read_parquet(facts_path)
        assert len(df_f) == 267658, f"Phase 6.8 facts count altered: {len(df_f)}"

        # 3. Phase 6.8 events
        events_path = PROJECT_ROOT / "data" / "processed" / "sec" / "eight_k" / "phase6_8_8k_events.parquet"
        assert events_path.exists()
        df_e = pd.read_parquet(events_path)
        assert len(df_e) == 4355, f"Phase 6.8 events count altered: {len(df_e)}"


class TestPointInTimeTemporalAlignment:
    """Verifies temporal cutoff arithmetic, daylight-saving transitions, and eligibility logic."""

    def test_market_close_daylight_saving_transitions(self):
        # Eastern Daylight Time (EDT, UTC-4): e.g. July 15, 2019
        close_edt = get_market_close_utc("2019-07-15")
        assert close_edt.hour == 20
        assert close_edt.minute == 0
        assert close_edt.tzname() == "UTC"

        # Eastern Standard Time (EST, UTC-5): e.g. January 15, 2019
        close_est = get_market_close_utc("2019-01-15")
        assert close_est.hour == 21
        assert close_est.minute == 0
        assert close_est.tzname() == "UTC"

    def test_before_close_filing_is_eligible(self):
        # Filing accepted at 15:30:00 EDT (19:30:00 UTC) on 2019-07-15
        acceptance = "2019-07-15 19:30:00+00:00"
        session_date = "2019-07-15"
        eligible = is_record_eligible_at_cutoff(acceptance, "2019-07-15", session_date)
        assert eligible is True, "Filing accepted before 16:00:00 NY must be eligible for session close"

    def test_after_close_filing_is_ineligible_for_same_session(self):
        # Filing accepted at 16:05:00 EDT (20:05:00 UTC) on 2019-07-15
        acceptance = "2019-07-15 20:05:00+00:00"
        session_date = "2019-07-15"
        eligible_same_day = is_record_eligible_at_cutoff(acceptance, "2019-07-15", session_date)
        assert eligible_same_day is False, "Filing accepted after 16:00:00 NY must be strictly ineligible for session T"

        # Eligible on next trading session T+1 (2019-07-16)
        eligible_next_day = is_record_eligible_at_cutoff(acceptance, "2019-07-15", "2019-07-16")
        assert eligible_next_day is True, "After-hours filing must become eligible on next trading session"

    def test_exact_cutoff_timestamp_is_eligible(self):
        # Filing accepted exactly at 16:00:00 EDT (20:00:00 UTC)
        acceptance = "2019-07-15 20:00:00+00:00"
        eligible = is_record_eligible_at_cutoff(acceptance, "2019-07-15", "2019-07-15")
        assert eligible is True, "Filing accepted exactly at cutoff is eligible"

    def test_conservative_date_only_fallback(self):
        # Record with no intraday time (midnight or has_intraday_time=False)
        # Same-day decision: must be REJECTED to prevent intraday lookahead
        eligible_same_day = is_record_eligible_at_cutoff(
            acceptance_timestamp=None,
            filing_date="2019-07-15",
            session_date="2019-07-15",
            has_intraday_time=False,
        )
        assert eligible_same_day is False, "Date-only record cannot enter same-day prediction"

        # Subsequent session decision: ACCEPTED
        eligible_subsequent = is_record_eligible_at_cutoff(
            acceptance_timestamp=None,
            filing_date="2019-07-15",
            session_date="2019-07-16",
            has_intraday_time=False,
        )
        assert eligible_subsequent is True, "Date-only record is eligible on subsequent trading dates"

    def test_missing_timestamp_and_date_excluded(self):
        eligible = is_record_eligible_at_cutoff(None, None, "2019-07-15")
        assert eligible is False, "Record lacking both timestamp and filing date must be excluded"


class TestRestatementAndLineageIsolation:
    """Verifies that subsequent amendments or restatements do not leak into historical as-of views."""

    def test_restatement_isolation(self):
        # Company reported Q1 2018 Revenue of 100M on 2018-05-01
        # Subsequently restated Q1 2018 Revenue to 95M in Form 10-K/A on 2019-03-15
        facts_data = [
            {
                "company_id": "US_TEST_001",
                "ticker": "TEST",
                "concept": "Revenues",
                "period_end": "2018-03-31",
                "form": "10-Q",
                "filed_date": "2018-05-01",
                "acceptance_timestamp": "2018-05-01 14:00:00+00:00",
                "accession_number": "0000001-18-000001",
                "value": 100000000.0,
            },
            {
                "company_id": "US_TEST_001",
                "ticker": "TEST",
                "concept": "Revenues",
                "period_end": "2018-03-31",
                "form": "10-K/A",
                "filed_date": "2019-03-15",
                "acceptance_timestamp": "2019-03-15 16:30:00+00:00",
                "accession_number": "0000001-19-000005",
                "value": 95000000.0,
            },
        ]
        df_facts = pd.DataFrame(facts_data)

        # As-of June 1, 2018 (Before restatement): Must observe original 100M
        as_of_2018 = filter_point_in_time_facts(df_facts, "2018-06-01 20:00:00+00:00")
        assert len(as_of_2018) == 1
        assert as_of_2018.iloc[0]["value"] == 100000000.0
        assert as_of_2018.iloc[0]["accession_number"] == "0000001-18-000001"

        # As-of April 1, 2019 (After restatement): Observes revised 95M
        as_of_2019 = filter_point_in_time_facts(df_facts, "2019-04-01 20:00:00+00:00")
        assert len(as_of_2019) == 1
        assert as_of_2019.iloc[0]["value"] == 95000000.0
        assert as_of_2019.iloc[0]["accession_number"] == "0000001-19-000005"


class TestRecoveredDatasets:
    """Verifies that Phase 6.9C recovered datasets meet schema, null, and coverage invariants."""

    def test_recovered_facts_dataset(self):
        facts_rec_path = PROJECT_ROOT / "data" / "processed" / "sec" / "phase6_9c" / "phase6_9c_financial_facts_recovered.parquet"
        assert facts_rec_path.exists(), "Recovered facts parquet must exist"
        df = pd.read_parquet(facts_rec_path)
        assert len(df) == 22384, f"Expected 22,384 facts, got {len(df)}"
        assert df["ticker"].nunique() == 24, f"Expected 24 recovered companies, got {df['ticker'].nunique()}"

        # Invariants: critical columns must have zero nulls
        for col in ["company_id", "cik", "ticker", "concept", "period_end", "form", "filed_date", "acceptance_timestamp", "accession_number", "value"]:
            assert df[col].isnull().sum() == 0, f"Unexpected nulls in {col}"

    def test_recovered_events_dataset(self):
        events_rec_path = PROJECT_ROOT / "data" / "processed" / "sec" / "phase6_9c" / "phase6_9c_8k_events_recovered.parquet"
        assert events_rec_path.exists(), "Recovered 8-K events parquet must exist"
        df = pd.read_parquet(events_rec_path)
        assert len(df) == 5159, f"Expected 5,159 events, got {len(df)}"
        assert df["ticker"].nunique() == 109, f"Expected 109 recovered companies, got {df['ticker'].nunique()}"

        # Invariants: critical columns must have zero nulls
        for col in ["company_id", "cik", "ticker", "form", "filing_date", "acceptance_timestamp", "accession_number"]:
            assert df[col].isnull().sum() == 0, f"Unexpected nulls in {col}"

    def test_consolidated_datasets_coverage(self):
        # 1. Consolidated facts
        facts_cons_path = PROJECT_ROOT / "data" / "processed" / "sec" / "phase6_9c" / "phase6_9c_financial_facts_consolidated.parquet"
        assert facts_cons_path.exists()
        df_f = pd.read_parquet(facts_cons_path)
        assert len(df_f) == 290042, f"Expected 290,042 facts, got {len(df_f)}"
        assert df_f["ticker"].nunique() == 323, f"Expected 323 tickers in facts, got {df_f['ticker'].nunique()}"

        # 2. Consolidated events
        events_cons_path = PROJECT_ROOT / "data" / "processed" / "sec" / "phase6_9c" / "phase6_9c_8k_events_consolidated.parquet"
        assert events_cons_path.exists()
        df_e = pd.read_parquet(events_cons_path)
        assert len(df_e) == 9514, f"Expected 9,514 events, got {len(df_e)}"
        assert df_e["ticker"].nunique() == 314, f"Expected 314 tickers in events, got {df_e['ticker'].nunique()}"

    def test_cohort_coverage_matrix(self):
        cov_path = PROJECT_ROOT / "data" / "processed" / "sec" / "phase6_9c" / "phase6_9c_company_coverage.csv"
        assert cov_path.exists()
        df_cov = pd.read_csv(cov_path)
        assert len(df_cov) == 305, "Coverage CSV must cover all 305 companies"
        assert df_cov["has_structured_facts"].sum() == 304, "304 companies must have facts (only CXO missing)"
        assert df_cov["has_8k_events"].sum() == 303, "303 companies must have events (APA predecessor review, CXO unresolved)"

        apa_row = df_cov[df_cov["ticker"] == "APA"].iloc[0]
        assert apa_row["events_status"] == "HISTORICAL_PREDECESSOR_REVIEW_REQUIRED"

        cxo_row = df_cov[df_cov["ticker"] == "CXO"].iloc[0]
        assert cxo_row["facts_status"] == "UNRESOLVED_MANIFEST_CIK_MISMAPPED"
        assert cxo_row["events_status"] == "UNRESOLVED_MANIFEST_CIK_MISMAPPED"


class TestVersion2HardeningAndFeatureBuilders:
    """Verifies Phase 6.9C V2 consolidation, identity resolution, and real feature engine anti-leakage."""

    def test_v2_datasets_100pct_cohort_coverage(self):
        cohort_path = PROJECT_ROOT / "data" / "processed" / "universe" / "phase6_9a1_cohort_manifest.csv"
        cohort = pd.read_csv(cohort_path)
        cohort_tickers = set(cohort["ticker"])

        # 1. Facts V2
        facts_v2_path = PROJECT_ROOT / "data" / "processed" / "sec" / "phase6_9c" / "phase6_9c_financial_facts_consolidated_v2.parquet"
        assert facts_v2_path.exists(), "Facts V2 parquet must exist"
        df_f2 = pd.read_parquet(facts_v2_path)
        assert len(df_f2) == 291269, f"Expected 291,269 facts, got {len(df_f2)}"
        cohort_facts_covered = set(df_f2["ticker"]).intersection(cohort_tickers)
        assert len(cohort_facts_covered) == 305, f"Expected 305 cohort companies in facts V2, got {len(cohort_facts_covered)}"

        # 2. Events V2
        events_v2_path = PROJECT_ROOT / "data" / "processed" / "sec" / "phase6_9c" / "phase6_9c_8k_events_consolidated_v2.parquet"
        assert events_v2_path.exists(), "Events V2 parquet must exist"
        df_e2 = pd.read_parquet(events_v2_path)
        assert len(df_e2) == 9571, f"Expected 9,571 events, got {len(df_e2)}"
        cohort_events_covered = set(df_e2["ticker"]).intersection(cohort_tickers)
        assert len(cohort_events_covered) == 305, f"Expected 305 cohort companies in events V2, got {len(cohort_events_covered)}"

        # 3. Coverage V2
        cov_v2_path = PROJECT_ROOT / "data" / "processed" / "sec" / "phase6_9c" / "phase6_9c_company_coverage_v2.csv"
        assert cov_v2_path.exists()
        df_cov2 = pd.read_csv(cov_v2_path)
        assert len(df_cov2) == 305
        assert df_cov2["has_structured_facts"].sum() == 305, "All 305 companies must have facts in V2"
        assert df_cov2["has_8k_events"].sum() == 305, "All 305 companies must have 8-K events in V2"

    def test_cxo_and_apa_identity_provenance(self):
        facts_v2_path = PROJECT_ROOT / "data" / "processed" / "sec" / "phase6_9c" / "phase6_9c_financial_facts_consolidated_v2.parquet"
        df_f2 = pd.read_parquet(facts_v2_path)

        # CXO facts: must preserve verified CIK 0001358071 and canonical company_id US_CIK_0001390532
        cxo_facts = df_f2[df_f2["ticker"] == "CXO"]
        assert len(cxo_facts) == 551, f"Expected 551 facts for CXO, got {len(cxo_facts)}"
        assert cxo_facts["cik"].iloc[0] == "0001358071"
        assert cxo_facts["company_id"].iloc[0] == "US_CIK_0001390532"

        # APA facts: must include predecessor Apache Corp CIK 0000006769
        apa_facts = df_f2[df_f2["ticker"] == "APA"]
        assert len(apa_facts) == 765, f"Expected 765 facts for APA (89 Phase 6.8 + 676 predecessor), got {len(apa_facts)}"
        assert "0000006769" in apa_facts["cik"].values
        assert "0001841666" in apa_facts["cik"].values

    def test_fundamental_feature_builder_anti_leakage(self):
        from src.features.fundamental import FundamentalFeatureEngine

        # Construct synthetic facts with after-cutoff fact and same-day date-only fact
        facts_data = [
            {
                "company_id": "US_LEAK_TEST",
                "ticker": "LEAK",
                "taxonomy": "us-gaap",
                "concept": "Revenues",
                "label": "Revenues",
                "period_start": "2019-01-01",
                "period_end": "2019-03-31",
                "fiscal_year": 2019,
                "fiscal_period": "Q1",
                "form": "10-Q",
                "filed_date": "2019-04-16",
                "acceptance_timestamp": "2019-04-16 15:00:00+00:00",  # Available before close
                "accession_number": "0001-19-001",
                "value": 1000000.0,
                "unit": "USD",
                "source": "sec_edgar_companyfacts",
            },
            {
                "company_id": "US_LEAK_TEST",
                "ticker": "LEAK",
                "taxonomy": "us-gaap",
                "concept": "NetIncomeLoss",
                "label": "Net Income",
                "period_start": "2019-01-01",
                "period_end": "2019-03-31",
                "fiscal_year": 2019,
                "fiscal_period": "Q1",
                "form": "10-Q",
                "filed_date": "2019-04-16",
                "acceptance_timestamp": "2019-04-16 20:30:00+00:00",  # After close (16:30 EDT = 20:30 UTC)
                "accession_number": "0001-19-002",
                "value": 200000.0,
                "unit": "USD",
                "source": "sec_edgar_companyfacts",
            },
            {
                "company_id": "US_LEAK_TEST",
                "ticker": "LEAK",
                "taxonomy": "us-gaap",
                "concept": "OperatingIncomeLoss",
                "label": "Operating Income",
                "period_start": "2019-01-01",
                "period_end": "2019-03-31",
                "fiscal_year": 2019,
                "fiscal_period": "Q1",
                "form": "10-Q",
                "filed_date": "2019-04-16",
                "acceptance_timestamp": "2019-04-16 00:00:00+00:00",  # Midnight date-only on decision day
                "accession_number": "0001-19-003",
                "value": 300000.0,
                "unit": "USD",
                "source": "sec_edgar_companyfacts",
            },
        ]
        df_f = pd.DataFrame(facts_data)
        engine = FundamentalFeatureEngine(df_facts=df_f)

        # Decision at session close on 2019-04-16 (16:00 EDT = 20:00 UTC)
        decision_close = pd.Timestamp("2019-04-16 20:00:00+00:00")
        snapshot = engine.get_as_of_snapshot("US_LEAK_TEST", decision_close)

        # 1. Before-close Revenue MUST be present
        assert snapshot["fundamental_available"] is True
        assert snapshot["fundamental_revenue"] == 1000000.0
        assert snapshot["fundamental_revenue_missing"] is False

        # 2. After-close Net Income (20:30 UTC) MUST be EXCLUDED (missing / NaN)
        assert pd.isna(snapshot["fundamental_net_income"])
        assert snapshot["fundamental_net_income_missing"] is True

        # 3. Same-day date-only Operating Income (midnight) MUST be EXCLUDED by conservative fallback
        assert pd.isna(snapshot["fundamental_operating_income"])
        assert snapshot["fundamental_operating_income_missing"] is True

    def test_event_feature_builder_anti_leakage(self):
        from src.features.event import SECEventFeatureEngine

        events_data = [
            {
                "company_id": "US_LEAK_EVENT",
                "cik": "0000001",
                "ticker": "LEAK",
                "form": "8-K",
                "filing_date": "2019-04-16",
                "acceptance_timestamp": "2019-04-16 19:40:00+00:00",  # 15:40 EDT (eligible before 16:00 close with 5m buffer)
                "accession_number": "0001-19-001",
                "items": "2.02,9.01",
                "primary_document": "doc1.htm",
                "filing_url": "url1",
                "source": "sec_edgar_submissions",
            },
            {
                "company_id": "US_LEAK_EVENT",
                "cik": "0000001",
                "ticker": "LEAK",
                "form": "8-K",
                "filing_date": "2019-04-16",
                "acceptance_timestamp": "2019-04-16 20:05:00+00:00",  # 16:05 EDT (after-hours, ineligible for session close)
                "accession_number": "0001-19-002",
                "items": "8.01",
                "primary_document": "doc2.htm",
                "filing_url": "url2",
                "source": "sec_edgar_submissions",
            },
        ]
        df_e = pd.DataFrame(events_data)
        engine = SECEventFeatureEngine(df_events=df_e)

        # Decision at market close on 2019-04-16 (20:00 UTC)
        decision_close = pd.Timestamp("2019-04-16 20:00:00+00:00")
        snapshot = engine.get_as_of_snapshot("US_LEAK_EVENT", decision_close, lookback_sessions=5)

        # Only the before-close 8-K should be counted (count == 1, earnings == 1)
        assert snapshot["sec_event_available"] is True
        assert snapshot["sec_event_count_5d"] == 1, f"Expected 1 event, got {snapshot['sec_event_count_5d']}"
        assert snapshot["sec_earnings_release_in_window"] == 1

        # Check next day session close (2019-04-17 20:00 UTC)
        snapshot_next = engine.get_as_of_snapshot("US_LEAK_EVENT", pd.Timestamp("2019-04-17 20:00:00+00:00"), lookback_sessions=5)
        # Both events are now eligible in trailing 5-day window
        assert snapshot_next["sec_event_count_5d"] == 2




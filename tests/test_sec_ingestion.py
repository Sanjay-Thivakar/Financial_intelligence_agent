"""
Unit and Integration Tests for SEC EDGAR Ingestion and Point-in-Time Validation.
"""

from datetime import datetime, timezone
import pandas as pd
import pytest

from src.data.sec.schema import PROCESSED_SEC_FACT_SCHEMA, PROCESSED_SEC_8K_SCHEMA
from src.data.sec.ingestor import SECIngestor, CORE_GAAP_CONCEPTS
from src.data.sec.validator import SECValidator


@pytest.fixture
def mock_universe_df():
    """Provides a small mock universe for SEC CIK resolution."""
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
            "company_id": "US_CIK_0001326801",
            "ticker": "META",
            "cik": "0001326801",
            "company_name": "Meta Platforms, Inc.",
            "sector": "Communication Services",
            "effective_from": "2022-06-09",
            "effective_to": None,
        },
    ])


@pytest.fixture
def mock_submissions_data():
    """Mock SEC submissions JSON response."""
    return {
        "cik": "0000320193",
        "name": "Apple Inc.",
        "tickers": ["AAPL"],
        "filings": {
            "recent": {
                "accessionNumber": [
                    "0000320193-24-000006",
                    "0000320193-24-000010",
                ],
                "form": ["10-Q", "8-K"],
                "filingDate": ["2024-02-01", "2024-02-01"],
                "reportDate": ["2023-12-30", "2024-02-01"],
                "acceptanceDateTime": [
                    "2024-02-01T18:15:30.000Z",
                    "2024-02-01T21:00:15.000Z",
                ],
                "primaryDocument": ["aapl-20231230.htm", "aapl-20240201_8k.htm"],
                "items": ["", "2.02,9.01"],
            }
        }
    }


@pytest.fixture
def mock_facts_data():
    """Mock SEC company facts JSON response."""
    return {
        "cik": 320193,
        "entityName": "Apple Inc.",
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "label": "Revenue",
                    "units": {
                        "USD": [
                            {
                                "start": "2023-10-01",
                                "end": "2023-12-30",
                                "val": 119575000000,
                                "accn": "0000320193-24-000006",
                                "fy": 2024,
                                "fp": "Q1",
                                "form": "10-Q",
                                "filed": "2024-02-01",
                            }
                        ]
                    }
                },
                "NetIncomeLoss": {
                    "label": "Net Income (Loss)",
                    "units": {
                        "USD": [
                            {
                                "start": "2023-10-01",
                                "end": "2023-12-30",
                                "val": 33916000000,
                                "accn": "0000320193-24-000006",
                                "fy": 2024,
                                "fp": "Q1",
                                "form": "10-Q",
                                "filed": "2024-02-01",
                            }
                        ]
                    }
                }
            }
        }
    }


class TestSECIngestion:
    def test_accession_map_parsing(self, mock_submissions_data):
        ingestor = SECIngestor()
        accn_map = ingestor.parse_submissions_accession_map(mock_submissions_data)

        assert "0000320193-24-000006" in accn_map
        meta = accn_map["0000320193-24-000006"]
        assert meta["form"] == "10-Q"
        assert meta["acceptance_datetime"] == "2024-02-01T18:15:30.000Z"

    def test_extract_8k_filings(self, mock_universe_df, mock_submissions_data):
        ingestor = SECIngestor(universe_df=mock_universe_df)
        df_8k = ingestor.extract_8k_filings("0000320193", mock_submissions_data)

        assert len(df_8k) == 1
        assert df_8k.iloc[0]["form"] == "8-K"
        assert df_8k.iloc[0]["items"] == "2.02,9.01"
        assert df_8k.iloc[0]["company_id"] == "US_CIK_0000320193"
        val_report = SECValidator.validate_8k_dataframe(df_8k)
        assert val_report["is_valid"] is True

    def test_extract_financial_facts_point_in_time(self, mock_universe_df, mock_submissions_data, mock_facts_data):
        ingestor = SECIngestor(universe_df=mock_universe_df)
        accn_map = ingestor.parse_submissions_accession_map(mock_submissions_data)
        df_facts = ingestor.extract_financial_facts("0000320193", mock_facts_data, accn_map)

        assert len(df_facts) == 2
        rev_row = df_facts[df_facts["concept"] == "Revenues"].iloc[0]
        assert rev_row["value"] == 119575000000.0
        assert rev_row["period_end"] == "2023-12-30"
        assert rev_row["filed_date"] == "2024-02-01"
        assert rev_row["company_id"] == "US_CIK_0000320193"

        # Check acceptance timestamp matches submission exactly
        expected_ts = pd.to_datetime("2024-02-01T18:15:30.000Z", utc=True)
        assert rev_row["acceptance_timestamp"] == expected_ts

        val_report = SECValidator.validate_facts_dataframe(df_facts)
        assert val_report["is_valid"] is True
        assert val_report["metrics"]["fatal_lookahead_records"] == 0

    def test_validator_catches_fatal_lookahead(self, mock_universe_df, mock_submissions_data, mock_facts_data):
        ingestor = SECIngestor(universe_df=mock_universe_df)
        accn_map = ingestor.parse_submissions_accession_map(mock_submissions_data)
        df_facts = ingestor.extract_financial_facts("0000320193", mock_facts_data, accn_map)

        # Introduce a deliberate fatal look-ahead error:
        # Acceptance timestamp precedes the period end date!
        df_corrupt = df_facts.copy()
        df_corrupt.loc[0, "acceptance_timestamp"] = pd.to_datetime("2023-12-01 00:00:00", utc=True)

        val_report = SECValidator.validate_facts_dataframe(df_corrupt)
        assert val_report["is_valid"] is False
        assert val_report["metrics"]["fatal_lookahead_records"] > 0
        assert any("FATAL LOOK-AHEAD ERROR" in err for err in val_report["errors"])

    def test_query_fact_as_of_prevents_lookahead(self, mock_universe_df, mock_submissions_data, mock_facts_data):
        ingestor = SECIngestor(universe_df=mock_universe_df)
        accn_map = ingestor.parse_submissions_accession_map(mock_submissions_data)
        df_facts = ingestor.extract_financial_facts("0000320193", mock_facts_data, accn_map)

        # Fact was accepted on 2024-02-01 18:15:30 UTC for period ending 2023-12-30
        # 1. Before public acceptance: must return None (zero look-ahead leakage)
        as_of_before = pd.Timestamp("2024-02-01 12:00:00", tz="UTC")
        fact_before = SECIngestor.query_fact_as_of(df_facts, "Revenues", "2023-12-30", as_of_before)
        assert fact_before is None

        # 2. After public acceptance: fact is available
        as_of_after = pd.Timestamp("2024-02-01 19:00:00", tz="UTC")
        fact_after = SECIngestor.query_fact_as_of(df_facts, "Revenues", "2023-12-30", as_of_after)
        assert fact_after is not None
        assert fact_after["value"] == 119575000000.0

    def test_query_fact_as_of_restatement_handling(self, mock_universe_df):
        # Test point-in-time restatement: original 10-K vs later 10-K/A amendment
        facts_records = [
            {
                "company_id": "US_CIK_0000320193",
                "cik": "0000320193",
                "ticker": "AAPL",
                "taxonomy": "us-gaap",
                "concept": "Assets",
                "label": "Total Assets",
                "period_start": None,
                "period_end": "2008-09-27",
                "fiscal_year": 2008,
                "fiscal_period": "FY",
                "form": "10-K",
                "filed_date": "2009-10-27",
                "acceptance_timestamp": pd.to_datetime("2009-10-27 17:00:00", utc=True),
                "accession_number": "0001193125-09-214859",
                "value": 39572000000.0,
                "unit": "USD",
                "source": "sec_edgar_companyfacts",
            },
            {
                "company_id": "US_CIK_0000320193",
                "cik": "0000320193",
                "ticker": "AAPL",
                "taxonomy": "us-gaap",
                "concept": "Assets",
                "label": "Total Assets",
                "period_start": None,
                "period_end": "2008-09-27",
                "fiscal_year": 2008,
                "fiscal_period": "FY",
                "form": "10-K/A",
                "filed_date": "2010-01-25",
                "acceptance_timestamp": pd.to_datetime("2010-01-25 17:00:00", utc=True),
                "accession_number": "0001193125-10-012091",
                "value": 36171000000.0,  # Restated value
                "unit": "USD",
                "source": "sec_edgar_companyfacts",
            },
        ]
        df_restated = pd.DataFrame(facts_records)

        # Cutoff 1: Prior to 10-K filing -> None
        cutoff_pre = pd.Timestamp("2009-10-01", tz="UTC")
        assert SECIngestor.query_fact_as_of(df_restated, "Assets", "2008-09-27", cutoff_pre) is None

        # Cutoff 2: After original 10-K but before 10-K/A amendment -> Must return original 10-K value
        cutoff_mid = pd.Timestamp("2009-11-15", tz="UTC")
        res_mid = SECIngestor.query_fact_as_of(df_restated, "Assets", "2008-09-27", cutoff_mid)
        assert res_mid is not None
        assert res_mid["form"] == "10-K"
        assert res_mid["value"] == 39572000000.0

        # Cutoff 3: After 10-K/A amendment -> Must return restated 10-K/A value
        cutoff_post = pd.Timestamp("2010-02-01", tz="UTC")
        res_post = SECIngestor.query_fact_as_of(df_restated, "Assets", "2008-09-27", cutoff_post)
        assert res_post is not None
        assert res_post["form"] == "10-K/A"
        assert res_post["value"] == 36171000000.0


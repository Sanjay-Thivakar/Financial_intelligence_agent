"""
Unit and Integration Tests for Phase 4B: Financial News Ingestion,
Point-in-Time Availability Filtering, and Baseline Feature Engineering.
"""

from datetime import datetime, timezone
import numpy as np
import pandas as pd
import pytest

from src.data.market.storage_policy import DataLayer, LicenseStatus, StoragePolicy
from src.data.news.schema import PROCESSED_NEWS_SCHEMA, NewsMappingStatus
from src.data.news.ingestor import NewsIngestor
from src.data.news.validator import NewsValidator
from src.data.universe.ticker_mapping import normalize_ticker
from src.features.config import NewsFeatureConfig
from src.features.news import NewsFeatureEngine
from src.features.market import MarketFeatureEngine
from src.features.fundamental import FundamentalFeatureEngine
from src.features.alignment import TemporalAligner, LookaheadLeakageError


@pytest.fixture
def mock_extended_universe_df():
    """Provides a universe with historical ticker changes, recycled tickers, and delisted intervals."""
    return pd.DataFrame([
        # Apple: continuous
        {
            "company_id": "US_CIK_0000320193",
            "ticker": "AAPL",
            "cik": "0000320193",
            "company_name": "Apple Inc.",
            "sector": "Information Technology",
            "effective_from": "1996-01-02",
            "effective_to": "9999-12-31",
        },
        # Meta: Ticker succession FB (2013-12-23 -> 2022-06-09) -> META (2022-06-09 -> present)
        {
            "company_id": "US_CIK_0001326801",
            "ticker": "FB",
            "cik": "0001326801",
            "company_name": "Meta Platforms, Inc.",
            "sector": "Communication Services",
            "effective_from": "2013-12-23",
            "effective_to": "2022-06-09",
        },
        {
            "company_id": "US_CIK_0001326801",
            "ticker": "META",
            "cik": "0001326801",
            "company_name": "Meta Platforms, Inc.",
            "sector": "Communication Services",
            "effective_from": "2022-06-09",
            "effective_to": "9999-12-31",
        },
        # Monsanto: Historical constituent (delisted 2018-06-07)
        {
            "company_id": "US_CIK_0001110783",
            "ticker": "MON",
            "cik": "0001110783",
            "company_name": "Monsanto Co",
            "sector": "Materials",
            "effective_from": "2002-08-28",
            "effective_to": "2018-06-07",
        },
        # Berkshire Hathaway Class B with dot notation
        {
            "company_id": "US_CIK_0001067983",
            "ticker": "BRK.B",
            "cik": "0001067983",
            "company_name": "Berkshire Hathaway Inc.",
            "sector": "Financials",
            "effective_from": "2010-02-12",
            "effective_to": "9999-12-31",
        },
        # Ambiguous overlapping fixture for testing collision handling
        {
            "company_id": "COMP_AMBIG_1",
            "ticker": "AMBIG",
            "cik": None,
            "company_name": "Ambiguous Co 1",
            "sector": "Industrials",
            "effective_from": "2020-01-01",
            "effective_to": "2021-12-31",
        },
        {
            "company_id": "COMP_AMBIG_2",
            "ticker": "AMBIG",
            "cik": None,
            "company_name": "Ambiguous Co 2",
            "sector": "Materials",
            "effective_from": "2020-06-01",
            "effective_to": "2022-06-01",
        },
    ])


@pytest.fixture
def mock_news_records_df():
    """Generates controlled synthetic news records for testing point-in-time filtering."""
    records = [
        # AAPL Article 1: 2023-05-24 14:00:00 UTC (intraday, 2 days before close cutoff)
        {
            "news_id": "aapl_news_1",
            "company_id": "US_CIK_0000320193",
            "ticker": "AAPL",
            "original_timestamp_raw": "2023-05-24 14:00:00 UTC",
            "published_at": pd.to_datetime("2023-05-24 14:00:00", utc=True),
            "published_date": "2023-05-24",
            "ingestion_timestamp": pd.to_datetime("2023-05-24 14:05:00", utc=True),
            "mapping_status": NewsMappingStatus.MATCHED.value,
            "mapping_provenance": "point_in_time_interval",
            "has_intraday_time": True,
            "has_body_text": True,
            "headline": "Apple expands supply chain investments",
            "article_text": "Apple announced major supply chain initiatives today.",
            "source": "Reuters",
            "url": "https://reuters.com/aapl-1",
            "source_dataset": "synthetic_fixture",
        },
        # AAPL Article 2: 2023-05-26 15:30:00 UTC (intraday, 4.5 hours before close cutoff at 20:00 UTC)
        {
            "news_id": "aapl_news_2",
            "company_id": "US_CIK_0000320193",
            "ticker": "AAPL",
            "original_timestamp_raw": "2023-05-26 11:30 am EDT",
            "published_at": pd.to_datetime("2023-05-26 15:30:00", utc=True),
            "published_date": "2023-05-26",
            "ingestion_timestamp": pd.to_datetime("2023-05-26 15:32:00", utc=True),
            "mapping_status": NewsMappingStatus.MATCHED.value,
            "mapping_provenance": "point_in_time_interval",
            "has_intraday_time": True,
            "has_body_text": False,  # Headline only
            "headline": "Apple introduces new App Store guidelines",
            "article_text": "",
            "source": "Benzinga",
            "url": "https://benzinga.com/aapl-2",
            "source_dataset": "synthetic_fixture",
        },
        # AAPL Article 3: 2023-05-26 20:30:00 UTC (intraday, AFTER close cutoff at 20:00 UTC)
        {
            "news_id": "aapl_news_3_future",
            "company_id": "US_CIK_0000320193",
            "ticker": "AAPL",
            "original_timestamp_raw": "2023-05-26 04:30 pm EDT",
            "published_at": pd.to_datetime("2023-05-26 20:30:00", utc=True),
            "published_date": "2023-05-26",
            "ingestion_timestamp": pd.to_datetime("2023-05-26 20:35:00", utc=True),
            "mapping_status": NewsMappingStatus.MATCHED.value,
            "mapping_provenance": "point_in_time_interval",
            "has_intraday_time": True,
            "has_body_text": True,
            "headline": "Post-close Apple analyst upgrades target price",
            "article_text": "Analyst released note following market close.",
            "source": "Bloomberg",
            "url": "https://bloomberg.com/aapl-3",
            "source_dataset": "synthetic_fixture",
        },
        # AAPL Article 4: Date-only for 2023-05-26 (00:00:00 UTC default)
        {
            "news_id": "aapl_news_4_dateonly",
            "company_id": "US_CIK_0000320193",
            "ticker": "AAPL",
            "original_timestamp_raw": "2023-05-26",
            "published_at": pd.to_datetime("2023-05-26 00:00:00", utc=True),
            "published_date": "2023-05-26",
            "ingestion_timestamp": pd.to_datetime("2023-05-26 01:00:00", utc=True),
            "mapping_status": NewsMappingStatus.MATCHED.value,
            "mapping_provenance": "point_in_time_interval",
            "has_intraday_time": False,
            "has_body_text": False,
            "headline": "Apple daily tech digest",
            "article_text": "",
            "source": "Nasdaq",
            "url": "https://nasdaq.com/aapl-4",
            "source_dataset": "synthetic_fixture",
        },
        # AAPL Article 5: Date-only for prior date 2023-05-20
        {
            "news_id": "aapl_news_5_priordate",
            "company_id": "US_CIK_0000320193",
            "ticker": "AAPL",
            "original_timestamp_raw": "2023-05-20",
            "published_at": pd.to_datetime("2023-05-20 00:00:00", utc=True),
            "published_date": "2023-05-20",
            "ingestion_timestamp": pd.to_datetime("2023-05-20 01:00:00", utc=True),
            "mapping_status": NewsMappingStatus.MATCHED.value,
            "mapping_provenance": "point_in_time_interval",
            "has_intraday_time": False,
            "has_body_text": True,
            "headline": "Apple weekly summary",
            "article_text": "Weekly retrospective on tech hardware.",
            "source": "Reuters",
            "url": "https://reuters.com/aapl-5",
            "source_dataset": "synthetic_fixture",
        },
    ]
    return pd.DataFrame(records)


class TestNewsSchemaAndMapping:
    def test_ticker_succession_point_in_time(self, mock_extended_universe_df):
        ingestor = NewsIngestor(universe_df=mock_extended_universe_df)

        # 1. FB before June 2022 maps to Meta
        cid_fb, status_fb, prov_fb = ingestor.resolve_company_mapping("FB", "2021-05-10")
        assert cid_fb == "US_CIK_0001326801"
        assert status_fb == NewsMappingStatus.MATCHED.value
        assert prov_fb == "point_in_time_interval"

        # 2. META after June 2022 maps to Meta
        cid_meta, status_meta, prov_meta = ingestor.resolve_company_mapping("META", "2023-01-15")
        assert cid_meta == "US_CIK_0001326801"
        assert status_meta == NewsMappingStatus.MATCHED.value

        # 3. FB in 2023 (after ticker change) must be OUT_OF_INTERVAL, NOT forced to Meta!
        cid_late_fb, status_late_fb, prov_late_fb = ingestor.resolve_company_mapping("FB", "2023-05-10")
        assert cid_late_fb is None
        assert status_late_fb == NewsMappingStatus.OUT_OF_INTERVAL.value

    def test_recycled_and_delisted_ticker_boundary(self, mock_extended_universe_df):
        ingestor = NewsIngestor(universe_df=mock_extended_universe_df)

        # MON while active in S&P 500 (e.g. 2015)
        cid_mon_act, stat_act, _ = ingestor.resolve_company_mapping("MON", "2015-06-01")
        assert cid_mon_act == "US_CIK_0001110783"
        assert stat_act == NewsMappingStatus.MATCHED.value

        # MON after acquisition by Bayer in 2018 (e.g. 2023)
        cid_mon_post, stat_post, _ = ingestor.resolve_company_mapping("MON", "2023-06-01")
        assert cid_mon_post is None
        assert stat_post == NewsMappingStatus.OUT_OF_INTERVAL.value

    def test_unmatched_and_ambiguous_symbols(self, mock_extended_universe_df):
        ingestor = NewsIngestor(universe_df=mock_extended_universe_df)

        # Completely unknown ticker
        cid_unk, stat_unk, prov_unk = ingestor.resolve_company_mapping("TOTALLY_UNKNOWN_XYZ", "2023-05-26")
        assert cid_unk is None
        assert stat_unk == NewsMappingStatus.UNMATCHED.value

        # Ambiguous overlapping interval
        cid_amb, stat_amb, prov_amb = ingestor.resolve_company_mapping("AMBIG", "2020-08-15")
        assert cid_amb is None
        assert stat_amb == NewsMappingStatus.AMBIGUOUS.value

    def test_ticker_punctuation_normalization(self, mock_extended_universe_df):
        ingestor = NewsIngestor(universe_df=mock_extended_universe_df)

        # Hyphenated, slashed, and dotted forms must normalize to BRK.B
        for raw in ["BRK-B", "BRK/B", "BRK.B", "  brk-b  "]:
            cid, stat, _ = ingestor.resolve_company_mapping(raw, "2023-05-26")
            assert cid == "US_CIK_0001067983"
            assert stat == NewsMappingStatus.MATCHED.value

    def test_deterministic_deduplication(self, mock_extended_universe_df):
        ingestor = NewsIngestor(universe_df=mock_extended_universe_df)
        raw_chunk = pd.DataFrame([
            {
                "Date": "2023-05-26 14:00:00 UTC",
                "Article_title": "Identical Headline",
                "Stock_symbol": "AAPL",
                "Publisher": "Reuters",
                "Article": "Body A",
            },
            {
                "Date": "2023-05-26 14:00:00 UTC",
                "Article_title": "Identical Headline",
                "Stock_symbol": "AAPL",
                "Publisher": "Reuters",
                "Article": "Body A duplicate",
            },
        ])
        processed = ingestor.process_csv_chunk(raw_chunk)
        assert len(processed) == 2
        # Deterministic IDs must match for true duplicate from same publisher
        assert processed.iloc[0]["news_id"] == processed.iloc[1]["news_id"]

    def test_distinct_sources_not_merged_on_identical_headline(self, mock_extended_universe_df):
        """
        Confirms that two distinct articles with identical tickers, headlines, and timestamps,
        but from different publishers/sources (e.g. Benzinga vs. Reuters) produce distinct stable IDs
        and are preserved rather than incorrectly merged, maintaining source provenance.
        """
        ingestor = NewsIngestor(universe_df=mock_extended_universe_df)
        raw_chunk = pd.DataFrame([
            {
                "Date": "2023-05-26 14:00:00 UTC",
                "Article_title": "Identical Wire Headline",
                "Stock_symbol": "AAPL",
                "Publisher": "Reuters",
                "Article": "Wire copy from Reuters",
                "Url": "https://reuters.com/article1",
            },
            {
                "Date": "2023-05-26 14:00:00 UTC",
                "Article_title": "Identical Wire Headline",
                "Stock_symbol": "AAPL",
                "Publisher": "Benzinga",
                "Article": "Wire copy syndicated on Benzinga",
                "Url": "https://benzinga.com/article2",
            },
        ])
        processed = ingestor.process_csv_chunk(raw_chunk)
        assert len(processed) == 2
        # Deterministic IDs must be different to preserve both articles and source provenance
        assert processed.iloc[0]["news_id"] != processed.iloc[1]["news_id"]
        assert processed.iloc[0]["source"] == "Reuters"
        assert processed.iloc[1]["source"] == "Benzinga"


class TestNewsPointInTimeFiltering:
    def test_strict_post_cutoff_exclusion(self, mock_news_records_df):
        """
        Decision cutoff: 2023-05-26 20:00:00 UTC (market close).
        - Article 1 (2023-05-24 14:00 UTC): eligible.
        - Article 2 (2023-05-26 15:30 UTC): eligible.
        - Article 3 (2023-05-26 20:30 UTC): strictly excluded (> cutoff).
        """
        engine = NewsFeatureEngine(mock_news_records_df)
        cutoff = pd.Timestamp("2023-05-26 20:00:00", tz="UTC")

        # Check eligibility method directly
        assert engine.is_article_eligible(
            article_pub_at=pd.Timestamp("2023-05-26 15:30:00", tz="UTC"),
            has_intraday_time=True,
            article_pub_date="2023-05-26",
            decision_timestamp=cutoff,
        ) is True

        assert engine.is_article_eligible(
            article_pub_at=pd.Timestamp("2023-05-26 20:30:00", tz="UTC"),
            has_intraday_time=True,
            article_pub_date="2023-05-26",
            decision_timestamp=cutoff,
        ) is False

    def test_date_only_same_day_protection(self, mock_news_records_df):
        """
        If an article has date-only timestamp (e.g. 2023-05-26 without intraday time):
        - On 2023-05-26 20:00:00 UTC cutoff: must be EXCLUDED (lookahead risk!).
        - On 2023-05-30 13:30:00 UTC cutoff (subsequent session): ELIGIBLE.
        """
        engine = NewsFeatureEngine(mock_news_records_df)
        same_day_cutoff = pd.Timestamp("2023-05-26 20:00:00", tz="UTC")
        subsequent_cutoff = pd.Timestamp("2023-05-30 13:30:00", tz="UTC")

        # Same-day cutoff rejects date-only record
        assert engine.is_article_eligible(
            article_pub_at=pd.Timestamp("2023-05-26 00:00:00", tz="UTC"),
            has_intraday_time=False,
            article_pub_date="2023-05-26",
            decision_timestamp=same_day_cutoff,
        ) is False

        # Subsequent session accepts prior date-only record
        assert engine.is_article_eligible(
            article_pub_at=pd.Timestamp("2023-05-26 00:00:00", tz="UTC"),
            has_intraday_time=False,
            article_pub_date="2023-05-26",
            decision_timestamp=subsequent_cutoff,
        ) is True

    def test_timezone_offsets_and_defensible_availability(self):
        """
        Tests parsing of EDT (UTC-4), EST (UTC-5), date-only, and malformed timestamps.
        Confirms that no article becomes eligible earlier than its defensible availability time.
        """
        ingestor = NewsIngestor()

        # EDT (UTC-4): 06:15 pm EDT = 18:15 EDT = 22:15 UTC
        dt_edt, date_edt, has_time_edt = ingestor.parse_datetime("September 12, 2023 — 06:15 pm EDT")
        assert has_time_edt is True
        assert date_edt == "2023-09-12"
        assert dt_edt == datetime(2023, 9, 12, 22, 15, tzinfo=timezone.utc)

        # EST (UTC-5): 08:52 am EST = 13:52 UTC
        dt_est, date_est, has_time_est = ingestor.parse_datetime("January 17, 2024 — 08:52 am EST")
        assert has_time_est is True
        assert date_est == "2024-01-17"
        assert dt_est == datetime(2024, 1, 17, 13, 52, tzinfo=timezone.utc)

        # Date-only: 2023-05-26
        dt_date, date_str, has_time_date = ingestor.parse_datetime("2023-05-26")
        assert has_time_date is False
        assert date_str == "2023-05-26"
        assert dt_date == datetime(2023, 5, 26, 0, 0, tzinfo=timezone.utc)

        # Malformed timestamps
        dt_bad, date_bad, has_time_bad = ingestor.parse_datetime("not-a-real-date-string")
        assert dt_bad is None
        assert date_bad is None
        assert has_time_bad is False

        # Eligibility check: EDT article is NOT available before 22:15 UTC
        engine = NewsFeatureEngine(pd.DataFrame())
        before_cutoff = pd.Timestamp("2023-09-12 21:00:00", tz="UTC")
        after_cutoff = pd.Timestamp("2023-09-12 22:30:00", tz="UTC")

        assert engine.is_article_eligible(
            article_pub_at=dt_edt,
            has_intraday_time=has_time_edt,
            article_pub_date=date_edt,
            decision_timestamp=before_cutoff,
        ) is False

        assert engine.is_article_eligible(
            article_pub_at=dt_edt,
            has_intraday_time=has_time_edt,
            article_pub_date=date_edt,
            decision_timestamp=after_cutoff,
        ) is True


class TestNewsFeatureEngine:
    def test_baseline_features_at_decision_cutoff(self, mock_news_records_df):
        """
        Tests calculation of baseline news features for AAPL at 2023-05-26 20:00:00 UTC:
        Eligible articles:
        - Article 1: 2023-05-24 14:00 (Reuters, with body, intraday) -> 2.25 days old (~54 hours)
        - Article 2: 2023-05-26 15:30 (Benzinga, no body, intraday) -> 0.1875 days old (4.5 hours)
        - Article 5: 2023-05-20 00:00 (Reuters, with body, date-only) -> 6.83 days old
        Excluded:
        - Article 3: 2023-05-26 20:30 (after cutoff)
        - Article 4: 2023-05-26 date-only (same day)
        """
        engine = NewsFeatureEngine(mock_news_records_df)
        cutoff = pd.Timestamp("2023-05-26 20:00:00", tz="UTC")
        snap = engine.get_as_of_snapshot("US_CIK_0000320193", cutoff)

        assert snap["news_available"] is True
        assert snap["news_missing"] is False

        # 1-day window (last 24 hours): only Article 2
        assert snap["news_count_1d"] == 1
        assert snap["news_unique_sources_1d"] == 1
        assert snap["news_has_body_ratio_1d"] == 0.0  # Benzinga headline only

        # 3-day window: Article 1 + Article 2
        assert snap["news_count_3d"] == 2
        assert snap["news_unique_sources_3d"] == 2  # Reuters + Benzinga
        assert snap["news_has_body_ratio_3d"] == 0.5  # 1 of 2 has body

        # 7-day window: Article 1 + Article 2 + Article 5
        assert snap["news_count_7d"] == 3
        assert snap["news_unique_sources_7d"] == 2

        # Recency in hours to latest eligible article (Article 2 at 15:30 UTC; cutoff is 20:00 UTC -> 4.5 hours)
        assert pytest.approx(snap["news_recency_hours"], abs=0.1) == 4.5

    def test_missing_company_snapshot(self, mock_news_records_df):
        engine = NewsFeatureEngine(mock_news_records_df)
        cutoff = pd.Timestamp("2023-05-26 20:00:00", tz="UTC")
        snap = engine.get_as_of_snapshot("NONEXISTENT_COMPANY", cutoff)

        assert snap["news_available"] is False
        assert snap["news_missing"] is True
        assert snap["news_article_count_missing"] is True
        assert snap["news_count_7d"] == 0
        assert np.isnan(snap["news_recency_hours"])
        assert np.isnan(snap["news_has_body_ratio_7d"])


class TestTemporalAlignmentWithNews:
    def test_three_way_alignment_market_fundamental_news(self, mock_extended_universe_df, mock_news_records_df):
        """Tests harmonizing Market, SEC Fundamentals, and Financial News in a single point-in-time vector."""
        df_market = pd.DataFrame([{
            "company_id": "US_CIK_0000320193",
            "ticker": "AAPL",
            "timestamp": pd.to_datetime("2023-05-26 00:00:00", utc=True),
            "trading_date": "2023-05-26",
            "open": 175.0, "high": 176.0, "low": 174.0, "close": 175.43,
            "adjusted_open": 175.0, "adjusted_high": 176.0, "adjusted_low": 174.0, "adjusted_close": 175.43,
            "volume": 50000000,
        }])

        df_facts = pd.DataFrame([{
            "company_id": "US_CIK_0000320193",
            "concept": "Revenues",
            "period_end": "2023-03-31",
            "form": "10-Q",
            "acceptance_timestamp": pd.to_datetime("2023-05-05 02:03:52", utc=True),
            "accession_number": "0000320193-23-000064",
            "value": 94836000000.0,
        }])

        mkt_engine = MarketFeatureEngine()
        fund_engine = FundamentalFeatureEngine(df_facts)
        news_engine = NewsFeatureEngine(mock_news_records_df)

        aligner = TemporalAligner(
            market_engine=mkt_engine,
            fundamental_engine=fund_engine,
            news_engine=news_engine,
            universe_df=mock_extended_universe_df,
        )

        aligned = aligner.align_features(df_market)
        assert len(aligned) == 1
        row = aligned.iloc[0]

        # 1. Market verification
        assert row["trading_date"] == "2023-05-26"
        assert row["decision_timestamp"] == pd.Timestamp("2023-05-26 20:00:00", tz="UTC")

        # 2. Fundamental verification
        assert row["fundamental_revenue"] == 94836000000.0
        assert bool(row["fundamental_revenue_missing"]) is False

        # 3. News verification
        assert bool(row["news_available"]) is True
        assert row["news_count_3d"] == 2
        assert pytest.approx(row["news_recency_hours"], abs=0.1) == 4.5


    def test_trailing_window_exact_boundaries(self):
        """
        Verifies trailing lookback windows have strict inclusive boundaries:
        [decision_timestamp - W_days, decision_timestamp].
        """
        cutoff = pd.Timestamp("2023-05-26 20:00:00", tz="UTC")
        boundary_news = pd.DataFrame([
            # Exactly on the 7-day boundary: 2023-05-19 20:00:00 UTC
            {
                "news_id": "on_boundary",
                "company_id": "US_CIK_0000320193",
                "ticker": "AAPL",
                "original_timestamp_raw": "2023-05-19 20:00:00 UTC",
                "published_at": pd.Timestamp("2023-05-19 20:00:00", tz="UTC"),
                "published_date": "2023-05-19",
                "has_intraday_time": True,
                "has_body_text": True,
                "headline": "On boundary headline",
                "article_text": "Text on boundary",
                "source": "Reuters",
                "url": "https://example.com/b1",
                "source_dataset": "synthetic_fixture",
            },
            # 1 second outside the 7-day boundary: 2023-05-19 19:59:59 UTC
            {
                "news_id": "outside_boundary",
                "company_id": "US_CIK_0000320193",
                "ticker": "AAPL",
                "original_timestamp_raw": "2023-05-19 19:59:59 UTC",
                "published_at": pd.Timestamp("2023-05-19 19:59:59", tz="UTC"),
                "published_date": "2023-05-19",
                "has_intraday_time": True,
                "has_body_text": True,
                "headline": "Outside boundary headline",
                "article_text": "Text outside boundary",
                "source": "Reuters",
                "url": "https://example.com/b2",
                "source_dataset": "synthetic_fixture",
            },
        ])
        engine = NewsFeatureEngine(boundary_news)
        snap = engine.get_as_of_snapshot("US_CIK_0000320193", cutoff)

        # 7-day window includes the exact boundary, but excludes the record 1s earlier
        assert snap["news_count_7d"] == 1
        # 14-day window includes both records
        assert snap["news_count_14d"] == 2

    def test_malformed_and_missing_timestamps(self):
        """Malformed or NaT publication timestamps must be safely ignored without raising exceptions."""
        malformed_df = pd.DataFrame([
            {
                "news_id": "bad_ts_1",
                "company_id": "US_CIK_0000320193",
                "ticker": "AAPL",
                "original_timestamp_raw": "invalid_date_string",
                "published_at": pd.NaT,
                "published_date": None,
                "has_intraday_time": False,
                "has_body_text": False,
                "headline": "Malformed date headline",
                "article_text": "",
                "source": "Unknown",
                "url": "",
                "source_dataset": "synthetic_fixture",
            }
        ])
        engine = NewsFeatureEngine(malformed_df)
        cutoff = pd.Timestamp("2023-05-26 20:00:00", tz="UTC")
        snap = engine.get_as_of_snapshot("US_CIK_0000320193", cutoff)
        assert snap["news_available"] is False
        assert snap["news_missing"] is True

    def test_feature_calculation_determinism(self, mock_news_records_df):
        """Running feature computation repeatedly on the same input yields identical results."""
        engine = NewsFeatureEngine(mock_news_records_df)
        decisions_df = pd.DataFrame([
            {"company_id": "US_CIK_0000320193", "decision_timestamp": pd.Timestamp("2023-05-26 20:00:00", tz="UTC")},
            {"company_id": "US_CIK_0000320193", "decision_timestamp": pd.Timestamp("2023-05-30 13:30:00", tz="UTC")},
        ])
        run1 = engine.compute_snapshots_for_decisions(decisions_df)
        run2 = engine.compute_snapshots_for_decisions(decisions_df)
        pd.testing.assert_frame_equal(run1, run2)


class TestNewsStoragePolicy:
    def test_fnspid_storage_governance(self):
        # Sample tier raw/normalized storage cannot be legally substantiated; must be UNVERIFIED and not permitted
        assert StoragePolicy.can_persist_locally("fnspid", DataLayer.RAW_RESPONSE, plan_tier="sample") is False
        assert StoragePolicy.can_persist_locally("fnspid", DataLayer.NORMALIZED_SERIES, plan_tier="sample") is False
        status_raw, _ = StoragePolicy.evaluate_storage_request("fnspid", DataLayer.RAW_RESPONSE, plan_tier="sample")
        assert status_raw == LicenseStatus.UNVERIFIED
        status_norm, _ = StoragePolicy.evaluate_storage_request("fnspid", DataLayer.NORMALIZED_SERIES, plan_tier="sample")
        assert status_norm == LicenseStatus.UNVERIFIED

        # Non-reversible derived features are permitted for internal research
        assert StoragePolicy.can_persist_locally("fnspid", DataLayer.DERIVED_FEATURES, plan_tier="sample") is True
        status_feat, _ = StoragePolicy.evaluate_storage_request("fnspid", DataLayer.DERIVED_FEATURES, plan_tier="sample")
        assert status_feat == LicenseStatus.PERMITTED

        # Full-universe persistent raw/normalized storage is UNVERIFIED / prohibited
        assert StoragePolicy.can_persist_locally("fnspid", DataLayer.RAW_RESPONSE, plan_tier="full_universe") is False
        assert StoragePolicy.can_persist_locally("fnspid", DataLayer.NORMALIZED_SERIES, plan_tier="full_universe") is False
        status_full_raw, _ = StoragePolicy.evaluate_storage_request("fnspid", DataLayer.RAW_RESPONSE, plan_tier="full_universe")
        assert status_full_raw == LicenseStatus.UNVERIFIED

        # Non-reversible derived features are permitted
        assert StoragePolicy.can_persist_locally("fnspid", DataLayer.DERIVED_FEATURES, plan_tier="full_universe") is True


"""
Unit and Integration Tests for Phase 2: FNSPID Market & News Ingestion.
"""

import os
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
import pytest

from src.data.market.schema import RAW_MARKET_SCHEMA, PROCESSED_MARKET_SCHEMA
from src.data.market.ingestor import MarketIngestor
from src.data.market.validator import MarketValidator
from src.data.news.schema import PROCESSED_NEWS_SCHEMA
from src.data.news.ingestor import NewsIngestor
from src.data.news.validator import NewsValidator


@pytest.fixture
def sample_universe_df():
    """Provides a miniature mock universe DataFrame."""
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
            "effective_to": None,
        },
    ])


class TestMarketIngestion:
    def test_market_chunk_processing(self, sample_universe_df):
        ingestor = MarketIngestor(universe_df=sample_universe_df)
        raw_df = pd.DataFrame([
            {
                "Date": "2023-10-15",
                "Open": 178.5,
                "High": 180.2,
                "Low": 177.9,
                "Close": 179.8,
                "Adj Close": 179.8,
                "Volume": 50000000,
            }
        ])
        processed = ingestor.process_csv_chunk(raw_df, ticker="AAPL")
        assert len(processed) == 1
        assert processed.iloc[0]["company_id"] == "US_CIK_0000320193"
        assert processed.iloc[0]["ticker"] == "AAPL"
        assert processed.iloc[0]["close"] == 179.8
        assert processed.iloc[0]["trading_date"] == "2023-10-15"

    def test_market_historical_ticker_succession(self, sample_universe_df):
        ingestor = MarketIngestor(universe_df=sample_universe_df)
        # FB in 2020 should resolve to US_CIK_0001326801
        cid_fb = ingestor.resolve_company_id("FB", "2020-01-15")
        assert cid_fb == "US_CIK_0001326801"

        # META in 2023 should resolve to same US_CIK_0001326801
        cid_meta = ingestor.resolve_company_id("META", "2023-01-15")
        assert cid_meta == "US_CIK_0001326801"

    def test_market_validator_valid(self):
        df = pd.DataFrame([
            {
                "company_id": "US_CIK_0000320193",
                "ticker": "AAPL",
                "timestamp": pd.to_datetime("2023-10-15 00:00:00+00:00", utc=True),
                "trading_date": "2023-10-15",
                "open": 178.5,
                "high": 180.2,
                "low": 177.9,
                "close": 179.8,
                "adjusted_close": 179.8,
                "volume": 50000000,
                "source": "fnspid_yfinance",
            }
        ])
        report = MarketValidator.validate_dataframe(df)
        assert report["is_valid"] is True
        assert report["total_records"] == 1
        assert len(report["errors"]) == 0

    def test_market_validator_detects_bad_prices(self):
        df = pd.DataFrame([
            {
                "company_id": "US_CIK_0000320193",
                "ticker": "AAPL",
                "timestamp": pd.to_datetime("2023-10-15 00:00:00+00:00", utc=True),
                "trading_date": "2023-10-15",
                "open": 0.0,  # Zero open price defect
                "high": 180.2,
                "low": 177.9,
                "close": 179.8,
                "adjusted_close": 179.8,
                "volume": 50000000,
                "source": "fnspid_yfinance",
            }
        ])
        report = MarketValidator.validate_dataframe(df)
        assert report["is_valid"] is False
        assert any("non-positive price" in e for e in report["errors"])


class TestNewsIngestion:
    def test_datetime_parsing_formats(self):
        # 1. UTC format
        dt1, iso1, intra1 = NewsIngestor.parse_datetime("2023-12-16 23:00:00 UTC")
        assert dt1 == datetime(2023, 12, 16, 23, 0, 0, tzinfo=timezone.utc)
        assert iso1 == "2023-12-16"
        assert intra1 is True

        # 2. EDT timezone format
        dt2, iso2, intra2 = NewsIngestor.parse_datetime("September 12, 2023 — 06:15 pm EDT")
        # 6:15 pm EDT = 18:15 EDT = 22:15 UTC
        assert dt2.hour == 22
        assert dt2.minute == 15
        assert intra2 is True

        # 3. Date only format
        dt3, iso3, intra3 = NewsIngestor.parse_datetime("2021-04-05")
        assert dt3.year == 2021
        assert dt3.month == 4
        assert dt3.day == 5
        assert intra3 is False

    def test_deterministic_news_id(self):
        nid1 = NewsIngestor.generate_news_id("AAPL", "2023-10-15T12:00:00Z", "Apple releases new M3 chips")
        nid2 = NewsIngestor.generate_news_id("AAPL", "2023-10-15T12:00:00Z", "Apple releases new M3 chips")
        nid3 = NewsIngestor.generate_news_id("AAPL", "2023-10-15T12:00:00Z", "Different headline")
        assert nid1 == nid2
        assert nid1 != nid3

    def test_news_chunk_processing(self, sample_universe_df):
        ingestor = NewsIngestor(universe_df=sample_universe_df)
        raw_df = pd.DataFrame([
            {
                "Date": "2023-10-15 14:30:00 UTC",
                "Article_title": "Apple hits record quarterly revenue",
                "Stock_symbol": "AAPL",
                "Url": "https://www.nasdaq.com/articles/apple-revenue",
                "Publisher": "Nasdaq",
                "Article": "Apple Inc reported record revenue today.",
            }
        ])
        processed = ingestor.process_csv_chunk(raw_df)
        assert len(processed) == 1
        row = processed.iloc[0]
        assert row["company_id"] == "US_CIK_0000320193"
        assert row["ticker"] == "AAPL"
        assert bool(row["has_intraday_time"]) is True
        assert row["headline"] == "Apple hits record quarterly revenue"
        assert row["article_text"] == "Apple Inc reported record revenue today."

    def test_news_validator_detects_empty_articles(self):
        df = pd.DataFrame([
            {
                "news_id": "hash123",
                "company_id": "US_CIK_0000320193",
                "ticker": "AAPL",
                "published_at": pd.to_datetime("2023-10-15 14:30:00+00:00", utc=True),
                "published_date": "2023-10-15",
                "has_intraday_time": True,
                "headline": "Headline with empty body",
                "article_text": "",  # Empty body text
                "source": "Benzinga",
                "url": "https://example.com",
                "source_dataset": "fnspid_all_external",
            }
        ])
        report = NewsValidator.validate_dataframe(df)
        assert report["is_valid"] is True  # Valid schema
        assert report["metrics"]["empty_article_text_pct"] == 100.0
        assert len(report["warnings"]) > 0
        assert any("empty article text" in w for w in report["warnings"])

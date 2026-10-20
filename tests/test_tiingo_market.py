"""
Unit and Integration Tests for Tiingo Market Data Ingestion and Validation.
"""

from datetime import datetime, timezone
import pandas as pd
import pytest

from src.data.market.tiingo_fetcher import TiingoFetcher, MissingCredentialsError
from src.data.market.tiingo_ingestor import TiingoIngestor, TIINGO_PROCESSED_MARKET_SCHEMA
from src.data.market.validator import MarketValidator


@pytest.fixture
def mock_universe_df():
    """Provides a small mock universe for Tiingo ticker mapping."""
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
    ])


@pytest.fixture
def mock_tiingo_raw_prices():
    """Mock Tiingo raw JSON prices response."""
    return [
        {
            "date": "2023-10-16T00:00:00.000Z",
            "open": 176.75,
            "high": 179.08,
            "low": 176.51,
            "close": 178.72,
            "volume": 52517000,
            "adjOpen": 176.01,
            "adjHigh": 178.33,
            "adjLow": 175.77,
            "adjClose": 177.97,
            "adjVolume": 52517000,
            "divCash": 0.0,
            "splitFactor": 1.0,
        },
        {
            "date": "2023-10-17T00:00:00.000Z",
            "open": 176.65,
            "high": 178.42,
            "low": 174.80,
            "close": 177.15,
            "volume": 57549400,
            "adjOpen": 175.91,
            "adjHigh": 177.67,
            "adjLow": 174.07,
            "adjClose": 176.41,
            "adjVolume": 57549400,
            "divCash": 0.24,
            "splitFactor": 1.0,
        },
    ]


class TestTiingoMarket:
    def test_tiingo_fetcher_requires_credentials(self, monkeypatch):
        monkeypatch.delenv("TIINGO_API_KEY", raising=False)
        monkeypatch.delenv("TIINGO_TOKEN", raising=False)
        fetcher = TiingoFetcher(api_key=None)
        assert fetcher.is_configured() is False

        with pytest.raises(MissingCredentialsError) as exc_info:
            fetcher.fetch_daily_prices("TEST_TICKER_UNCACHED", force_refresh=True)
        assert "TIINGO_API_KEY" in str(exc_info.value)

    def test_tiingo_ingestion_normalization(self, mock_universe_df, mock_tiingo_raw_prices):
        ingestor = TiingoIngestor(universe_df=mock_universe_df)
        df = ingestor.normalize_tiingo_prices("AAPL", mock_tiingo_raw_prices)

        assert len(df) == 2
        assert df.iloc[0]["company_id"] == "US_CIK_0000320193"
        assert df.iloc[0]["ticker"] == "AAPL"
        assert df.iloc[0]["trading_date"] == "2023-10-16"
        assert df.iloc[0]["open"] == 176.75
        assert df.iloc[0]["adjusted_open"] == 176.01
        assert df.iloc[0]["split_factor"] == 1.0
        assert df.iloc[1]["dividend_cash"] == 0.24

        # Validate with standard MarketValidator
        val_report = MarketValidator.validate_dataframe(df)
        assert val_report["is_valid"] is True
        assert val_report["metrics"]["non_positive_prices"] == 0
        assert val_report["metrics"]["high_low_inversions"] == 0

    def test_calculate_session_coverage_accounts_for_holidays(self):
        # In 2023: 260 M-F business days minus 10 NYSE/NASDAQ holidays = 250 trading days
        start_date = "2023-01-01"
        end_date = "2023-12-31"

        # Simulating 2 observed dates out of 250
        cov = MarketValidator.calculate_session_coverage(["2023-10-16", "2023-10-17"], start_date, end_date)
        assert cov["expected_business_days"] == 260
        assert cov["exchange_holidays"] == 10
        assert cov["expected_sessions"] == 250
        assert cov["observed_sessions"] == 2
        assert cov["missing_count"] == 248
        assert cov["coverage_pct"] == 0.8


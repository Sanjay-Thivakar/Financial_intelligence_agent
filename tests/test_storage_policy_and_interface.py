"""
Unit Tests for Provider-Independent Market Data Abstraction and License-Aware Storage Policy.
"""

import pytest
import pandas as pd
from typing import Dict, List, Any, Optional

from src.data.market.base import BaseMarketFetcher, BaseMarketIngestor, MissingCredentialsError
from src.data.market.tiingo_fetcher import TiingoFetcher
from src.data.market.tiingo_ingestor import TiingoIngestor
from src.data.market.storage_policy import DataLayer, LicenseStatus, StoragePolicy


class MockMarketFetcher(BaseMarketFetcher):
    """Mock provider adapter for testing provider-independence."""

    @property
    def provider_name(self) -> str:
        return "mock_provider"

    def is_configured(self) -> bool:
        return True

    def fetch_daily_prices(
        self,
        ticker: str,
        start_date: str,
        end_date: Optional[str] = None,
        force_refresh: bool = False,
    ) -> List[Dict[str, Any]]:
        return [
            {
                "date": f"{start_date}T00:00:00.000Z",
                "open": 100.0,
                "high": 105.0,
                "low": 99.0,
                "close": 104.0,
                "volume": 1000000,
            }
        ]

    def fetch_ticker_metadata(
        self,
        ticker: str,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        return {"ticker": ticker, "name": f"Mock Company {ticker}"}


class MockMarketIngestor(BaseMarketIngestor):
    """Mock normalizer conforming to BaseMarketIngestor."""

    def normalize_prices(
        self,
        ticker: str,
        raw_records: List[Dict[str, Any]],
    ) -> pd.DataFrame:
        records = []
        for r in raw_records:
            records.append({
                "company_id": f"MOCK_{ticker}",
                "ticker": ticker,
                "timestamp": pd.to_datetime(r["date"], utc=True),
                "trading_date": r["date"][:10],
                "open": r["open"],
                "high": r["high"],
                "low": r["low"],
                "close": r["close"],
                "volume": r["volume"],
                "source": "mock_provider",
            })
        return pd.DataFrame(records)


class TestMarketInterface:
    def test_mock_adapter_implements_base_interface(self):
        fetcher = MockMarketFetcher()
        assert fetcher.provider_name == "mock_provider"
        assert fetcher.is_configured() is True

        raw_prices = fetcher.fetch_daily_prices("TEST", "2023-01-03")
        assert len(raw_prices) == 1
        assert raw_prices[0]["close"] == 104.0

        meta = fetcher.fetch_ticker_metadata("TEST")
        assert meta["name"] == "Mock Company TEST"

        ingestor = MockMarketIngestor()
        df = ingestor.normalize_prices("TEST", raw_prices)
        assert len(df) == 1
        assert df.iloc[0]["company_id"] == "MOCK_TEST"
        assert df.iloc[0]["close"] == 104.0

    def test_tiingo_fetcher_and_ingestor_conform_to_base(self):
        # TiingoFetcher is an instance of BaseMarketFetcher
        fetcher = TiingoFetcher(api_key="mock_test_token")
        assert isinstance(fetcher, BaseMarketFetcher)
        assert fetcher.provider_name == "tiingo"
        assert fetcher.is_configured() is True

        # TiingoIngestor is an instance of BaseMarketIngestor
        ingestor = TiingoIngestor()
        assert isinstance(ingestor, BaseMarketIngestor)

        # Standard normalize_prices delegates to normalize_tiingo_prices
        raw_mock = [{
            "date": "2023-01-03T00:00:00.000Z",
            "open": 150.0, "high": 152.0, "low": 149.0, "close": 151.0,
            "adjOpen": 150.0, "adjHigh": 152.0, "adjLow": 149.0, "adjClose": 151.0,
            "volume": 500000, "adjVolume": 500000, "divCash": 0.0, "splitFactor": 1.0
        }]
        df = ingestor.normalize_prices("AAPL", raw_mock)
        assert len(df) == 1
        assert df.iloc[0]["close"] == 151.0
        assert df.iloc[0]["source"] == "tiingo_eod"


class TestStoragePolicy:
    def test_sec_edgar_allows_all_layers(self):
        for layer in DataLayer:
            assert StoragePolicy.can_persist_locally("sec_edgar", layer) is True
            status, reason = StoragePolicy.evaluate_storage_request("sec_edgar", layer)
            assert status == LicenseStatus.PERMITTED
            assert "Public Domain" in reason

    def test_tiingo_starter_restricts_raw_and_normalized(self):
        # Starter plan prohibits persistent raw responses and database archives
        assert StoragePolicy.can_persist_locally("tiingo", DataLayer.RAW_RESPONSE, plan_tier="starter") is False
        assert StoragePolicy.can_persist_locally("tiingo", DataLayer.NORMALIZED_SERIES, plan_tier="starter") is False

        status_raw, reason_raw = StoragePolicy.evaluate_storage_request("tiingo", DataLayer.RAW_RESPONSE, plan_tier="starter")
        assert status_raw == LicenseStatus.PROHIBITED
        assert "memory processing only" in reason_raw

        status_norm, reason_norm = StoragePolicy.evaluate_storage_request("tiingo", DataLayer.NORMALIZED_SERIES, plan_tier="starter")
        assert status_norm == LicenseStatus.PROHIBITED
        assert "without enterprise license" in reason_norm

        # But permits derived mathematical features and model outputs
        assert StoragePolicy.can_persist_locally("tiingo", DataLayer.DERIVED_FEATURES, plan_tier="starter") is True
        assert StoragePolicy.can_persist_locally("tiingo", DataLayer.MODEL_OUTPUTS, plan_tier="starter") is True

    def test_tiingo_power_permits_internal_persistence(self):
        # Power tier ($30/mo) permits internal caching & research database for the subscriber
        assert StoragePolicy.can_persist_locally("tiingo", DataLayer.RAW_RESPONSE, plan_tier="power") is True
        assert StoragePolicy.can_persist_locally("tiingo", DataLayer.NORMALIZED_SERIES, plan_tier="power") is True
        assert StoragePolicy.can_persist_locally("tiingo", DataLayer.DERIVED_FEATURES, plan_tier="power") is True
        assert StoragePolicy.can_persist_locally("tiingo", DataLayer.MODEL_OUTPUTS, plan_tier="power") is True

    def test_yfinance_prohibited_due_to_tos(self):
        # Automated yfinance scraping has no persistent archiving license
        assert StoragePolicy.can_persist_locally("yfinance", DataLayer.RAW_RESPONSE, plan_tier="unauthorized") is False
        assert StoragePolicy.can_persist_locally("yfinance", DataLayer.NORMALIZED_SERIES, plan_tier="unauthorized") is False

    def test_polygon_developer_vs_free(self):
        # Developer tier permits internal storage
        assert StoragePolicy.can_persist_locally("polygon", DataLayer.RAW_RESPONSE, plan_tier="developer") is True
        assert StoragePolicy.can_persist_locally("polygon", DataLayer.NORMALIZED_SERIES, plan_tier="developer") is True

        # Free tier restricts persistent storage
        assert StoragePolicy.can_persist_locally("polygon", DataLayer.RAW_RESPONSE, plan_tier="free") is False
        assert StoragePolicy.can_persist_locally("polygon", DataLayer.NORMALIZED_SERIES, plan_tier="free") is False
        assert StoragePolicy.can_persist_locally("polygon", DataLayer.DERIVED_FEATURES, plan_tier="free") is True

    def test_wrds_academic_license(self):
        # WRDS academic subscription permits internal research database
        assert StoragePolicy.can_persist_locally("wrds", DataLayer.RAW_RESPONSE, plan_tier="academic") is True
        assert StoragePolicy.can_persist_locally("wrds", DataLayer.NORMALIZED_SERIES, plan_tier="academic") is True
        assert StoragePolicy.can_persist_locally("wrds", DataLayer.DERIVED_FEATURES, plan_tier="academic") is True
        assert StoragePolicy.can_persist_locally("wrds", DataLayer.MODEL_OUTPUTS, plan_tier="academic") is True

    def test_unknown_provider_defaults_to_unverified(self):
        assert StoragePolicy.can_persist_locally("unknown_vendor", DataLayer.NORMALIZED_SERIES) is False
        status, reason = StoragePolicy.evaluate_storage_request("unknown_vendor", DataLayer.NORMALIZED_SERIES)
        assert status == LicenseStatus.UNVERIFIED

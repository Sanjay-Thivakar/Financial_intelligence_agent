"""
Market Data ingestion and processing package.
"""

from src.data.market.schema import (
    RAW_MARKET_SCHEMA,
    PROCESSED_MARKET_SCHEMA,
    MARKET_FIELD_STATUS,
)
from src.data.market.base import (
    BaseMarketFetcher,
    BaseMarketIngestor,
    MissingCredentialsError,
)
from src.data.market.tiingo_fetcher import TiingoFetcher
from src.data.market.tiingo_ingestor import TiingoIngestor, TIINGO_PROCESSED_MARKET_SCHEMA
from src.data.market.storage_policy import DataLayer, LicenseStatus, StoragePolicy

__all__ = [
    "RAW_MARKET_SCHEMA",
    "PROCESSED_MARKET_SCHEMA",
    "MARKET_FIELD_STATUS",
    "BaseMarketFetcher",
    "BaseMarketIngestor",
    "TiingoFetcher",
    "MissingCredentialsError",
    "TiingoIngestor",
    "TIINGO_PROCESSED_MARKET_SCHEMA",
    "DataLayer",
    "LicenseStatus",
    "StoragePolicy",
]


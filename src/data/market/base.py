"""
Provider-Independent Market Data Abstraction.

Defines abstract base classes and protocols for historical market data fetchers
and ingestors, ensuring downstream feature engineering, validation, and decision
logic remain decoupled from specific commercial providers.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
import pandas as pd


class MissingCredentialsError(Exception):
    """Raised when an API provider requires credentials that are not configured."""
    def __init__(self, provider: str, env_var: str):
        super().__init__(
            f"Missing required API credentials for {provider}. "
            f"Please set the {env_var} environment variable or add it to a local .env file."
        )
        self.provider = provider
        self.env_var = env_var


class BaseMarketFetcher(ABC):
    """Abstract interface for historical market data fetchers."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the data provider (e.g. 'tiingo', 'polygon', 'yfinance')."""
        pass

    @abstractmethod
    def is_configured(self) -> bool:
        """Returns True if the fetcher has valid credentials/configuration."""
        pass

    @abstractmethod
    def fetch_daily_prices(
        self,
        ticker: str,
        start_date: str,
        end_date: Optional[str] = None,
        force_refresh: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Fetches raw daily price observations for a given ticker and date range.
        Returns a list of raw records (dicts).
        """
        pass

    @abstractmethod
    def fetch_ticker_metadata(
        self,
        ticker: str,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """
        Fetches reference metadata (company name, exchange, active dates) for a ticker.
        """
        pass


class BaseMarketIngestor(ABC):
    """Abstract interface for normalizing raw provider responses into canonical schema."""

    @abstractmethod
    def normalize_prices(
        self,
        ticker: str,
        raw_records: List[Dict[str, Any]],
    ) -> pd.DataFrame:
        """
        Normalizes raw provider price dictionaries into a DataFrame conforming
        to the project's canonical market schema.
        """
        pass

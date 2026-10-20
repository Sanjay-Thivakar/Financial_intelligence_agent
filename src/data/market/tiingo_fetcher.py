"""
Tiingo Historical Market Data API Client.

Retrieves daily EOD stock prices, splits, and dividend distributions
from api.tiingo.com while handling rate limits and credential verification.
Never hardcodes secrets.
"""

import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Any, Optional
import requests

from src.config import get_tiingo_api_key
from src.data.market.base import BaseMarketFetcher, MissingCredentialsError

logger = logging.getLogger(__name__)


class TiingoFetcher(BaseMarketFetcher):
    """Client for Tiingo Daily Stock Price and Reference endpoints."""

    BASE_URL = "https://api.tiingo.com/tiingo/daily"

    @property
    def provider_name(self) -> str:
        return "tiingo"

    def __init__(
        self,
        api_key: Optional[str] = None,
        raw_dir: str = "data/raw/market/tiingo",
    ):
        self.api_key = api_key or get_tiingo_api_key()
        self.raw_dir = Path(raw_dir)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()

    def is_configured(self) -> bool:
        """Checks if a usable API token is available."""
        return bool(self.api_key and self.api_key.strip())

    def _get_headers(self) -> Dict[str, str]:
        """Constructs authorization headers."""
        if not self.is_configured():
            raise MissingCredentialsError(provider="Tiingo", env_var="TIINGO_API_KEY")
        return {
            "Content-Type": "application/json",
            "Authorization": f"Token {self.api_key.strip()}",
        }

    def fetch_ticker_metadata(self, ticker: str, force_refresh: bool = False) -> Dict[str, Any]:
        """Fetches metadata for a ticker (exchange, startDate, endDate, isActive)."""
        ticker_clean = ticker.upper().strip()
        cache_file = self.raw_dir / f"{ticker_clean}_meta.json"

        if cache_file.exists() and not force_refresh:
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)

        url = f"{self.BASE_URL}/{ticker_clean}"
        headers = self._get_headers()
        logger.info(f"Fetching Tiingo metadata for {ticker_clean} from {url}")

        resp = self.session.get(url, headers=headers, timeout=30)
        if resp.status_code == 404:
            logger.warning(f"Ticker {ticker_clean} not found on Tiingo (HTTP 404)")
            return {}
        resp.raise_for_status()

        data = resp.json()
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return data

    def fetch_daily_prices(
        self,
        ticker: str,
        start_date: str = "2020-01-01",
        end_date: Optional[str] = None,
        force_refresh: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Fetches daily OHLCV prices, splits, and dividends for a ticker.
        Preserves raw JSON response in data/raw/market/tiingo/<TICKER>_prices.json.
        """
        ticker_clean = ticker.upper().strip()
        cache_file = self.raw_dir / f"{ticker_clean}_prices.json"

        if cache_file.exists() and not force_refresh:
            logger.debug(f"Loading cached Tiingo prices for {ticker_clean} from {cache_file}")
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)

        url = f"{self.BASE_URL}/{ticker_clean}/prices"
        params = {"startDate": start_date, "format": "json"}
        if end_date:
            params["endDate"] = end_date

        headers = self._get_headers()
        logger.info(f"Fetching Tiingo prices for {ticker_clean} (start={start_date}) from {url}")

        resp = self.session.get(url, headers=headers, params=params, timeout=30)
        if resp.status_code == 404:
            logger.warning(f"Ticker {ticker_clean} prices not found on Tiingo (HTTP 404)")
            return []
        resp.raise_for_status()

        data = resp.json()
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return data

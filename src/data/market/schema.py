"""
Market Data Schema Definitions.

Defines the normalized schema for raw and processed market data.
Preserves temporal alignment fields and corporate identity foreign keys.
"""

from dataclasses import dataclass
import pyarrow as pa


# Raw market data schema as provided by FNSPID (Yahoo Finance scrape)
RAW_MARKET_SCHEMA = pa.schema([
    ("Date", pa.string()),
    ("Open", pa.float64()),
    ("High", pa.float64()),
    ("Low", pa.float64()),
    ("Close", pa.float64()),
    ("Adj Close", pa.float64()),
    ("Volume", pa.int64()),
])

# Processed market data schema aligned to S&P 500 universe
PROCESSED_MARKET_SCHEMA = pa.schema([
    ("company_id", pa.string()),          # Foreign key to sp500_universe (e.g. US_CIK_0000320193)
    ("ticker", pa.string()),              # Normalized uppercase ticker symbol (e.g. AAPL)
    ("timestamp", pa.timestamp("us", tz="UTC")), # Trading day timestamp at UTC midnight (00:00:00 UTC)
    ("trading_date", pa.string()),        # ISO date YYYY-MM-DD for fast date-partitioned filtering
    ("open", pa.float64()),               # Split-adjusted opening price
    ("high", pa.float64()),               # Split-adjusted session high
    ("low", pa.float64()),                # Split-adjusted session low
    ("close", pa.float64()),              # Split-adjusted unadjusted close price
    ("adjusted_close", pa.float64()),     # Dividend & split adjusted close price
    ("volume", pa.int64()),               # Trading volume (number of shares traded)
    ("source", pa.string()),              # Provenance tag: e.g. "fnspid_yfinance"
])

# Summary of availability
MARKET_FIELD_STATUS = {
    "company_id": "Derived via S&P 500 universe point-in-time mapper",
    "ticker": "Available from filename in FNSPID zip",
    "timestamp": "Available at Daily granularity (YYYY-MM-DD); NO intraday/bar time",
    "trading_date": "Available (YYYY-MM-DD)",
    "open": "Available in FNSPID",
    "high": "Available in FNSPID",
    "low": "Available in FNSPID",
    "close": "Available in FNSPID",
    "adjusted_close": "Available in FNSPID ('Adj Close')",
    "volume": "Available in FNSPID",
    "source": "Recorded as 'fnspid_yfinance'",
    "intraday_timestamp": "UNAVAILABLE in FNSPID (strictly daily close)",
    "vwap": "UNAVAILABLE in FNSPID",
    "bid_ask_spread": "UNAVAILABLE in FNSPID",
}

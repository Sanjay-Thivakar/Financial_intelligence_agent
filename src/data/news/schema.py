"""
Financial News Schema Definitions.

Defines the normalized canonical schema for raw and processed financial news data.
Preserves temporal alignment fields, publication timestamps, corporate identity foreign keys,
provenance metadata, and timestamp/text quality indicators.
"""

from enum import Enum
from typing import Dict
import pyarrow as pa


class NewsMappingStatus(str, Enum):
    """Documented status of ticker-to-canonical-company mapping."""
    MATCHED = "MATCHED"                  # Ticker was active S&P 500 constituent on publication date
    OUT_OF_INTERVAL = "OUT_OF_INTERVAL"  # Ticker exists in S&P 500 history, but not active on publication date
    UNMATCHED = "UNMATCHED"              # Ticker not found in S&P 500 canonical registry
    AMBIGUOUS = "AMBIGUOUS"              # Multiple overlapping entities active for same ticker on publication date


# Raw news schema as provided in FNSPID All_external.csv
RAW_NEWS_ALL_EXTERNAL_SCHEMA = pa.schema([
    ("Date", pa.string()),
    ("Article_title", pa.string()),
    ("Stock_symbol", pa.string()),
    ("Url", pa.string()),
    ("Publisher", pa.string()),
    ("Author", pa.string()),
    ("Article", pa.string()),
    ("Lsa_summary", pa.string()),
    ("Luhn_summary", pa.string()),
    ("Textrank_summary", pa.string()),
    ("Lexrank_summary", pa.string()),
])

# Raw news schema as provided in FNSPID nasdaq_exteral_data.csv
RAW_NEWS_NASDAQ_SCHEMA = pa.schema([
    ("Unnamed: 0", pa.string()),
    ("Date", pa.string()),
    ("Article_title", pa.string()),
    ("Stock_symbol", pa.string()),
    ("Url", pa.string()),
    ("Publisher", pa.string()),
    ("Author", pa.string()),
    ("Article", pa.string()),
    ("Lsa_summary", pa.string()),
    ("Luhn_summary", pa.string()),
    ("Textrank_summary", pa.string()),
    ("Lexrank_summary", pa.string()),
])

# Processed canonical news schema aligned to S&P 500 universe and point-in-time rules
PROCESSED_NEWS_SCHEMA = pa.schema([
    ("news_id", pa.string()),                        # Deterministic hash ID based on ticker, published_at, and headline
    ("company_id", pa.string()),                     # Foreign key to sp500_universe (None if unmatched / out-of-interval)
    ("ticker", pa.string()),                         # Normalized uppercase ticker symbol
    ("original_timestamp_raw", pa.string()),        # Original raw date string from source
    ("published_at", pa.timestamp("us", tz="UTC")), # Timezone-normalized publication timestamp in UTC
    ("published_date", pa.string()),                 # ISO date YYYY-MM-DD for fast date-partitioned filtering
    ("ingestion_timestamp", pa.timestamp("us", tz="UTC")), # Timezone-aware UTC timestamp when record was ingested
    ("mapping_status", pa.string()),                 # MATCHED, OUT_OF_INTERVAL, UNMATCHED, AMBIGUOUS
    ("mapping_provenance", pa.string()),             # e.g. "point_in_time_interval", "unmatched_symbol"
    ("has_intraday_time", pa.bool_()),               # True if published_at has sub-daily time; False if date-only default
    ("has_body_text", pa.bool_()),                   # True if article_text is populated and non-empty
    ("headline", pa.string()),                       # Article headline / title
    ("article_text", pa.string()),                   # Full body text (empty string when missing in raw source)
    ("source", pa.string()),                         # Scraped source publisher (e.g. Benzinga, Nasdaq, Reuters)
    ("url", pa.string()),                            # Original article URL
    ("source_dataset", pa.string()),                 # Provenance tag: e.g. "fnspid_all_external", "synthetic_test"
])

# Summary of field availability and constraints
NEWS_FIELD_STATUS: Dict[str, str] = {
    "news_id": "Generated deterministically via sha256(ticker + published_at + headline)",
    "company_id": "Derived via S&P 500 universe point-in-time mapper (strict interval check)",
    "ticker": "Available in FNSPID ('Stock_symbol')",
    "original_timestamp_raw": "Preserved verbatim from source 'Date' column",
    "published_at": "Normalized to UTC; mixed sub-second, second, minute, or date-only formats",
    "published_date": "Extracted ISO date (YYYY-MM-DD)",
    "ingestion_timestamp": "Recorded at ingestion time in UTC",
    "mapping_status": "Documented status: MATCHED, OUT_OF_INTERVAL, UNMATCHED, AMBIGUOUS",
    "mapping_provenance": "Documented method: point_in_time_interval, unmatched_symbol, etc.",
    "has_intraday_time": "Derived (True if hour/minute available, False if date-only midnight default)",
    "has_body_text": "Derived (True if non-empty body text present, False if headline-only)",
    "headline": "Available in FNSPID ('Article_title')",
    "article_text": "PARTIALLY UNAVAILABLE: empty in large chunks of All_external.csv; present in nasdaq_exteral_data.csv",
    "source": "Available in All_external ('Publisher'); mostly empty in nasdaq_exteral_data",
    "url": "Available in FNSPID ('Url')",
    "source_dataset": "Recorded explicitly ('fnspid_all_external' or 'synthetic_fixture')",
    "author": "UNAVAILABLE / ~100% missing in evaluated samples",
    "sentiment_ground_truth": "UNAVAILABLE in raw data (only model-generated scores)",
}

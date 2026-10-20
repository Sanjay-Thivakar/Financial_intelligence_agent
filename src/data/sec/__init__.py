"""
SEC EDGAR Data Module.

Provides SEC filing retrieval, XBRL fundamental fact parsing,
point-in-time acceptance timestamp alignment, and data validation.
"""

from src.data.sec.schema import PROCESSED_SEC_FACT_SCHEMA, PROCESSED_SEC_8K_SCHEMA, PROCESSED_SEC_EVENT_SCHEMA
from src.data.sec.fetcher import SECFetcher
from src.data.sec.ingestor import SECIngestor, SECEventExtractor, CORE_GAAP_CONCEPTS
from src.data.sec.validator import SECValidator

__all__ = [
    "PROCESSED_SEC_FACT_SCHEMA",
    "PROCESSED_SEC_8K_SCHEMA",
    "PROCESSED_SEC_EVENT_SCHEMA",
    "SECFetcher",
    "SECIngestor",
    "SECEventExtractor",
    "CORE_GAAP_CONCEPTS",
    "SECValidator",
]


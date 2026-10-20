"""
SEC EDGAR Data Schema Definitions.

Defines schemas for raw submissions metadata, raw XBRL facts,
and processed point-in-time fundamental statement records.
"""

import pyarrow as pa

# Processed fundamental fact schema with point-in-time temporal availability
PROCESSED_SEC_FACT_SCHEMA = pa.schema([
    ("company_id", pa.string()),          # Foreign key to sp500_universe (e.g. US_CIK_0000320193)
    ("cik", pa.string()),                 # 10-digit zero-padded SEC Central Index Key
    ("ticker", pa.string()),              # Point-in-time trading symbol
    ("taxonomy", pa.string()),            # e.g. "us-gaap", "dei"
    ("concept", pa.string()),             # GAAP concept tag (e.g. Revenues, NetIncomeLoss)
    ("label", pa.string()),               # Human-readable concept description
    ("period_start", pa.string()),        # ISO date YYYY-MM-DD (or None for instant balance sheet items)
    ("period_end", pa.string()),          # Fiscal period end date (YYYY-MM-DD)
    ("fiscal_year", pa.int32()),          # Fiscal year (e.g. 2023)
    ("fiscal_period", pa.string()),       # e.g. "Q1", "Q2", "Q3", "FY"
    ("form", pa.string()),                # Filing form type (e.g. 10-K, 10-Q)
    ("filed_date", pa.string()),          # Official filing date (YYYY-MM-DD)
    ("acceptance_timestamp", pa.timestamp("us", tz="UTC")), # Exact public availability timestamp (UTC)
    ("accession_number", pa.string()),    # Unique SEC filing accession identifier (e.g. 0000320193-24-000006)
    ("value", pa.float64()),              # Numerical fact value
    ("unit", pa.string()),                # e.g. "USD", "shares", "pure"
    ("source", pa.string()),              # Provenance tag: "sec_edgar_companyfacts"
])

# Processed SEC 8-K material event metadata schema
PROCESSED_SEC_8K_SCHEMA = pa.schema([
    ("company_id", pa.string()),          # Foreign key to sp500_universe
    ("cik", pa.string()),                 # 10-digit zero-padded SEC CIK
    ("ticker", pa.string()),              # Point-in-time trading symbol
    ("form", pa.string()),                # "8-K" or "8-K/A"
    ("filing_date", pa.string()),         # ISO date YYYY-MM-DD
    ("acceptance_timestamp", pa.timestamp("us", tz="UTC")), # Exact public availability timestamp (UTC)
    ("accession_number", pa.string()),    # Unique accession identifier
    ("items", pa.string()),               # Comma-separated reported items (e.g. "2.02,9.01")
    ("primary_document", pa.string()),    # Document filename (e.g. aapl-20240201.htm)
    ("filing_url", pa.string()),          # Direct URL to filing directory on SEC EDGAR
    ("source", pa.string()),              # Provenance tag: "sec_edgar_submissions"
])

# Processed SEC 8-K Corporate Event Schema with full provenance and validation status
PROCESSED_SEC_EVENT_SCHEMA = pa.schema([
    ("company_id", pa.string()),          # Foreign key to sp500_universe
    ("cik", pa.string()),                 # 10-digit zero-padded SEC CIK
    ("ticker", pa.string()),              # Point-in-time trading symbol
    ("form", pa.string()),                # "8-K" or "8-K/A"
    ("filing_date", pa.string()),         # ISO date YYYY-MM-DD
    ("acceptance_timestamp", pa.timestamp("us", tz="UTC")), # Exact public availability timestamp (UTC) or null
    ("accession_number", pa.string()),    # Unique accession identifier
    ("items", pa.string()),               # Comma-separated reported items (e.g. "2.02,9.01")
    ("primary_document", pa.string()),    # Document filename
    ("filing_url", pa.string()),          # Direct URL to filing directory on SEC EDGAR
    ("is_amendment", pa.bool_()),         # True if form is 8-K/A
    ("data_availability_status", pa.string()), # "eligible", "missing_timestamp", "malformed"
    ("parsing_status", pa.string()),      # "success", "partial", "error"
    ("source", pa.string()),              # Provenance tag
])


# S&P 500 Universe Data Quality Report

**Execution Timestamp (UTC):** 2026-10-06T05:37:58.517305+00:00  
**Overall Validation Status:** `PASSED_WITH_WARNINGS`  

## Summary Metrics

| Metric | Count | Notes |
| :--- | :--- | :--- |
| Total Membership Records | **1,265** | Historical & active intervals |
| Total Unique Tickers | **1,211** | Point-in-time trading symbols |
| Total Unique Companies | **1,169** | Canonical company IDs |
| Currently Active Constituents | **503** | Open interval (effective_to is None) |
| Records with Resolved CIK | **902** | Standardized 10-digit SEC CIK |
| Records with Missing CIK | **363** | Delisted historical firms flagged |
| Duplicate Company Rows | **0** | Duplicate exact intervals |
| Duplicate Active CIKs | **3** | Legitimate dual-class shares |
| Invalid Ticker Symbols | **0** | Malformed tickers |
| Overlapping Intervals | **0** | Overlapping ticker time series |

## Data Quality Findings

### Duplicate Active CIKs (Dual Share Classes) (3 items)

| Severity | Identifier | Description | Details |
| :--- | :--- | :--- | :--- |
| `INFO` | `CIK_0001564708` | Multiple active share classes share the same corporate CIK identity | cik=0001564708, tickers=['NWSA', 'NWS'] |
| `INFO` | `CIK_0001652044` | Multiple active share classes share the same corporate CIK identity | cik=0001652044, tickers=['GOOGL', 'GOOG'] |
| `INFO` | `CIK_0001754301` | Multiple active share classes share the same corporate CIK identity | cik=0001754301, tickers=['FOXA', 'FOX'] |

### Missing CIKs (Historical Delisted Entities) (363 items)

| Severity | Identifier | Description | Details |
| :--- | :--- | :--- | :--- |
| `WARNING` | `ABI` | SEC CIK could not be resolved from EDGAR active registries | company_name=ABI, effective_from=1996-01-02, effective_to=2008-11-24 |
| `WARNING` | `ABKFQ` | SEC CIK could not be resolved from EDGAR active registries | company_name=ABKFQ, effective_from=2000-12-11, effective_to=2008-06-11 |
| `WARNING` | `ABS` | SEC CIK could not be resolved from EDGAR active registries | company_name=Albertsons, effective_from=1996-01-02, effective_to=2006-06-02 |
| `WARNING` | `ABX` | SEC CIK could not be resolved from EDGAR active registries | company_name=ABX, effective_from=1996-01-02, effective_to=2002-07-22 |
| `WARNING` | `ACAS` | SEC CIK could not be resolved from EDGAR active registries | company_name=American Capital, effective_from=2007-07-09, effective_to=2009-03-04 |
| `WARNING` | `ACKH` | SEC CIK could not be resolved from EDGAR active registries | company_name=ACKH, effective_from=1996-01-02, effective_to=2000-11-17 |
| `WARNING` | `ACS` | SEC CIK could not be resolved from EDGAR active registries | company_name=ACS, effective_from=2004-04-02, effective_to=2010-02-08 |
| `WARNING` | `ADS` | SEC CIK could not be resolved from EDGAR active registries | company_name=Alliance Data Systems, effective_from=2013-12-23, effective_to=2020-06-22 |
| `WARNING` | `AFS.A` | SEC CIK could not be resolved from EDGAR active registries | company_name=AFS.A, effective_from=1998-04-08, effective_to=2000-12-01 |
| `WARNING` | `AGC` | SEC CIK could not be resolved from EDGAR active registries | company_name=AGC, effective_from=1996-01-02, effective_to=2001-08-29 |
| `WARNING` | `AHM` | SEC CIK could not be resolved from EDGAR active registries | company_name=AHM, effective_from=1996-01-02, effective_to=1998-10-01 |
| `WARNING` | `AMCC` | SEC CIK could not be resolved from EDGAR active registries | company_name=AMCC, effective_from=2001-01-02, effective_to=2006-05-18 |
| `WARNING` | `ANDV` | SEC CIK could not be resolved from EDGAR active registries | company_name=Andeavor, effective_from=2007-09-27, effective_to=2018-10-01 |
| `WARNING` | `ANRZQ` | SEC CIK could not be resolved from EDGAR active registries | company_name=ANRZQ, effective_from=2011-06-02, effective_to=2012-10-02 |
| `WARNING` | `ANV` | SEC CIK could not be resolved from EDGAR active registries | company_name=ANV, effective_from=1996-01-02, effective_to=1999-04-12 |
| `INFO` | ... | *[Truncated: 348 more items]* | - |

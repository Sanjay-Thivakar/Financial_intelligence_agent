# S&P 500 Company Universe & Identity Layer (Phase 1)

## Overview & Objective

This repository contains the **Phase 1** foundational data infrastructure for an **AI-powered financial intelligence agent for US equities**.

The broader research objective is to develop an open, modular framework that evaluates how different financial information modalities (earnings calls, 10-K/10-Q filings, price/volume dynamics, alternative text feeds) contribute to risk-aware **BUY / HOLD / SELL** investment decisions.

To establish sound quantitative research, **survivorship bias must be eliminated**. Evaluating historical investment models solely on today's surviving S&P 500 constituents introduces severe look-ahead and survivorship distortion. This module constructs a **point-in-time historical company universe** and **canonical company-identity layer** spanning 1996 through present.

---

## Data Sources & Provenance

| Data Asset | Source Origin | Retrieval Endpoint | Format | Scope |
| :--- | :--- | :--- | :--- | :--- |
| **Current S&P 500 Constituents** | Wikipedia (Curated S&P DJI Feed) | `https://en.wikipedia.org/wiki/List_of_S%26P_500_companies` | HTML Table / JSON / CSV | Current 503 constituent share classes with GICS sectors & CIKs |
| **Historical Changes & Corporate Actions** | Wikipedia (S&P Components Archive) | `https://en.wikipedia.org/wiki/Historical_components_of_the_S%26P_500` | HTML Table / JSON / CSV | 400+ additions, deletions, mergers, spin-offs, and ticker changes |
| **Historical Membership Intervals** | Curated S&P 500 Historical Repository | `https://raw.githubusercontent.com/fja05680/sp500/master/sp500_ticker_start_end.csv` | CSV | 1,260+ point-in-time intervals from 1996 to 2026 |
| **Historical Daily Snapshots** | Hanshof Constituents Archive | `https://raw.githubusercontent.com/hanshof/sp500_constituents/master/` | CSV | Historical daily membership matrix & founding/CIK metadata |
| **SEC Ticker & CIK Registry** | SEC EDGAR Public Filings Directory | SEC EDGAR Mirror / `company_tickers.json` | JSON | 9,998 exchange-listed tickers mapped to official SEC CIKs |

**Retrieval Metadata:**  
All pristine raw files are archived under `data/raw/universe/`. A machine-readable manifest with timestamps, hashes, and record counts is recorded in `data/raw/universe/retrieval_metadata.json`.

---

## Canonical Data Dictionary

The processed output is saved to both `data/processed/universe/sp500_universe.parquet` and `data/processed/universe/sp500_universe.csv`.

| Column | Type | Nullable | Description | Example |
| :--- | :--- | :--- | :--- | :--- |
| `company_id` | `string` | **No** | Stable canonical entity identifier. Standard format is `US_CIK_<10-digit-cik>` when CIK is known; `COMP_NO_CIK_<ticker>` fallback when CIK is unassigned. | `US_CIK_0001326801` |
| `ticker` | `string` | **No** | Point-in-time stock exchange trading symbol. | `FB` (historical), `META` (current) |
| `cik` | `string` | **Yes** | 10-digit zero-padded SEC Central Index Key for EDGAR filings integration. | `0001326801` |
| `company_name` | `string` | **No** | Full corporate / security name. | `Meta Platforms, Inc.` |
| `sector` | `string` | **Yes** | GICS Sector classification. | `Communication Services` |
| `effective_from` | `string` | **No** | Start date of membership interval under this ticker (`YYYY-MM-DD`). | `2013-12-23` |
| `effective_to` | `string` | **Yes** | End date of membership interval (`YYYY-MM-DD`). `None` indicates currently active. | `2022-06-09` |

### Interval Convention
Membership intervals follow **half-open interval semantics**: `[effective_from, effective_to)`.
- A company was an active constituent on date $T$ if:
  $$\text{effective\_from} \le T < \text{effective\_to} \quad (\text{or } \text{effective\_to is null})$$
- Ticker changes that take effect on date $D$ record `effective_to = D` for the predecessor symbol and `effective_from = D` for the successor symbol, guaranteeing zero gaps and zero overlap.

---

## Transformations & Data Cleansing

1. **Ticker Symbol Normalization**:
   - Converted hyphenated share class symbols (e.g., `BRK-B`, `BF-B`) to market standard dot notation (`BRK.B`, `BF.B`).
   - Standardized all symbols to uppercase alphanumeric strings with optional single dot notation.
2. **Temporal Interval Reconciliation**:
   - Fused historical interval records with the latest addition/removal events (e.g., September 21, 2026 changes: additions of `BE`, `P`, `ILMN` and retirements of `TAP`, `TTD`, `BLDR`).
   - Guaranteed that active constituent rows (`effective_to is None`) match the 503 live S&P 500 constituents.
3. **Company Identity & Ticker Succession Linking**:
   - When a company underwent a ticker change (e.g. `FB` $\to$ `META`, `CDAY` $\to$ `DAY`, `WLTW` $\to$ `WTW`, `ANTM` $\to$ `ELV`), the entity is recognized under the same `company_id` and SEC CIK (`0001326801`, `0001725057`, `0001140536`, `0001156039`).
   - Downstream models querying filings, fundamentals, and earnings calls can traverse the entire corporate history seamlessly.
4. **Reused Ticker Disambiguation**:
   - Addressed symbol reuse across distinct historical eras. For example, ticker `Q` represented **Qwest Communications International Inc.** (`CIK 0001037949`) from 2000 to 2011, and was subsequently reused in November 2025 by **Qnity Electronics** (`CIK 0002058873`, DuPont spin-off). The pipeline correctly binds separate canonical `company_id`s to each respective era.
5. **Strict Validation Pipeline**:
   - Automated validator (`UniverseValidator`) enforces zero duplicate records, zero interval overlaps, valid ticker syntax, and catalogs missing CIKs.

---

## Data Quality Summary & Findings

Validation execution details (saved in `data/processed/universe/universe_data_quality_report.json`):

| Check | Result | Explanation |
| :--- | :--- | :--- |
| **Total Records** | **1,265** | 762 historical intervals + 503 active intervals |
| **Unique Tickers** | **1,211** | Point-in-time trading symbols |
| **Canonical Companies** | **1,169** | Distinct corporate identities |
| **Duplicate Company Rows** | **0** | No identical duplicate intervals |
| **Invalid Tickers** | **0** | All tickers adhere to US market specifications |
| **Overlapping Intervals** | **0** | Strict interval disjointness verified |
| **Dual Share Classes** | **3** | Alphabet (`GOOG`/`GOOGL`), Fox (`FOX`/`FOXA`), News Corp (`NWS`/`NWSA`) |
| **Resolved SEC CIKs** | **902 (71.3%)** | Mapped to 10-digit EDGAR CIKs |
| **Missing CIKs** | **363 (28.7%)** | Historical delisted firms flagged (see below) |

---

## Known Limitations & Guidelines for Downstream Phases

1. **Delisted Historical Entities (Pre-2015 / Pre-EDGAR)**:
   - 363 historical constituent intervals represent companies that were acquired, liquidated, or went private prior to modern digital EDGAR tracking (e.g., pre-2010 mergers).
   - Rather than fabricating dummy CIKs or discarding non-surviving firms, these entities are explicitly retained with `cik = None` and a deterministic ID (`COMP_NO_CIK_<ticker>`).
   - Downstream Phase 2 pricing ingestion should query market feeds (CRSP, Yahoo Finance, AlphaVantage) using `ticker` and interval dates.
2. **Dual Share Classes**:
   - 3 corporations issue dual share classes in the index:
     - Alphabet Inc. (`GOOG` Class C, `GOOGL` Class A) $\to$ `US_CIK_0001652044`
     - Fox Corporation (`FOX` Class B, `FOXA` Class A) $\to$ `US_CIK_0001754301`
     - News Corp (`NWS` Class B, `NWSA` Class A) $\to$ `US_CIK_0001564708`
   - Total active ticker symbols equal 503, representing 500 distinct corporations.
3. **Point-in-Time Querying**:
   - To avoid survivorship bias in Phase 2+ backtests, **always** use the built-in query method:
     ```python
     from src.data.universe.builder import UniverseBuilder
     import pandas as pd

     universe = pd.read_parquet("data/processed/universe/sp500_universe.parquet")
     historical_constituents = UniverseBuilder.get_constituents_at_date(universe, "2008-09-15")
     ```
   - This returns the exact constituent list as it existed on September 15, 2008 (including Lehman Brothers `LEHMQ`, Bear Stearns, etc.), preventing forward-looking bias.

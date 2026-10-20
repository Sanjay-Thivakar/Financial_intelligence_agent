# Phase 2 — FNSPID Market & Financial News Data Evaluation & Ingestion Report

## Executive Summary & Audit Reconciliation

Phase 2 evaluated the **Financial News and Stock Price Integration Dataset (FNSPID)** as the primary candidate for historical market prices and financial news for our S&P 500 financial intelligence agent.

Rather than blindly downloading all ~29.6 GB of uncompressed data, we executed a remote discovery, ZIP central directory parsing, and chunked streaming inspection pipeline.

### Core Verdict: **REJECTED AS PRIMARY V1 HISTORICAL DATASET**
*(Accepted strictly as an auxiliary exploratory text sample / secondary benchmark).*

The quantitative audit reconciles all sample vs. full-dataset metrics and confirms that FNSPID cannot serve as the production foundation for an S&P 500 decision agent due to:
1. **Survivorship & Historical Coverage Bias**: Over **58.3% of historical/delisted S&P 500 constituents (413 of 708 symbols) are absent** from FNSPID's market price series. Backtesting on FNSPID introduces severe survivorship bias.
2. **Active Constituent Deficiencies**: **56 active S&P 500 constituents (11.1%) are missing** from the market price series, including `META` (only predecessor `FB` is tracked, terminating in June 2022), `UNH` (UnitedHealth Group), dual-class share classes (`BRK.B`, `BF.B` due to unhandled dot notation), and recently added index members (`PLTR`, `KVUE`, `GEV`, `SOLV`, `COIN`, `DASH`).
3. **Empty News Body Text in Primary Aggregator**: In `All_external.csv` (5.73 GB, ~10M records), **100.0% of evaluated external news items have completely empty `Article` body texts**, containing only headlines and raw URLs.
4. **Look-Ahead Bias via Date-Only News Records**: Many news records contain only day-level date stamps (`YYYY-MM-DD` or `%d-%b-%y` normalized to 00:00:00 UTC) without publication hour or minute, creating look-ahead leakage when evaluated against intraday trading decisions.
5. **Abrupt 2023 Cutoff & Unadjusted Historical Price Artifacts**: All price series terminate in **late December 2023**, with historical series displaying unadjusted data artifacts (e.g. 959 records in `JPM` prior to 1984 record `open = 0.0`).

---

## 1. Audit Reconciliation of Metrics

During Phase 2 exploration, initial preliminary logs reported partial counts from initial range-bounded probes before the complete ZIP directory structure was isolated. This audit formally reconciles all figures:

| Metric | Preliminary Probe (Truncated Range) | Final Reconciled Full Dataset | Root Cause / Audit Explanation |
| :--- | :--- | :--- | :--- |
| **FNSPID Market Tickers in Zip** | 3,772 / 4,425 | **7,693 unique tickers** | The ZIP Central Directory is **1,602,175 bytes** (offset `587,923,399` to `589,525,573`) containing 15,388 total entries. Initial probes fetched only a 900 KB tail slice, capturing only the second half of the directory. The full Central Directory contains exactly **7,693 valid CSV files** (`full_history/<TICKER>.csv`) and 7,694 macOS AppleDouble resource forks (`__MACOSX/._*.csv`). |
| **Total Universe Ticker Overlap** | 381 / 1,211 (31.5%) | **742 / 1,211 (61.27%)** | Full-range parsing covers all 1,211 universe tickers against the 7,693 FNSPID tickers. 469 historical/active symbols remain missing. |
| **Active S&P 500 Overlap** | 221 / 503 (43.9%) | **447 / 503 (88.87%)** | In the full directory, mega-caps (`AAPL`, `MSFT`, `AMZN`, `GOOG`, `TSLA`, `NVDA`, `JPM`, `JNJ`, `V`, `WMT`, `PG`, `XOM`) are present. 56 active tickers remain missing. |
| **Historical S&P 500 Overlap** | 160 / 708 (22.6%) | **295 / 708 (41.67%)** | 413 historical delisted/acquired constituents are absent, causing survivorship distortion. |
| **Market Sample Rows** | 45,812 rows | **45,770 rows** | First download hit a minor EOF chunk boundary on `AA` and `AAPL`. The verified raw CSVs in `data/raw/market/` contain: `AA` (15,605) + `JPM` (11,040) + `AAPL` (10,852) + `GOOG` (4,874) + `TSLA` (3,399) = **45,770 rows**, matching `sp500_market_sample.parquet` exactly (1-to-1). |
| **News Sample Rows** | 8,367 rows | **8,830 rows** | The pristine 2.0 MB raw download `fnspid_all_external_sample.csv` contains **8,922 data rows**. `NewsIngestor` detected and dropped exactly **92 duplicate records** (`news_id` match), producing exactly **8,830 rows** in `fnspid_news_processed.parquet`. |

---

## 2. Dataset Source & Provenance

| Attribute | Details |
| :--- | :--- |
| **Dataset Title** | FNSPID: Financial News and Stock Price Integration Dataset |
| **Original Paper** | *"FNSPID: A Comprehensive Financial News Dataset in Time Series"*, Zihan Dong, Xinyu Fan, Zhiyuan Peng (arXiv:2402.06698, accepted at KDD 2024 Applied Data Science Track) |
| **Paper URL** | `https://arxiv.org/abs/2402.06698` |
| **Hugging Face Repository** | `https://huggingface.co/datasets/Zihan1004/FNSPID` |
| **GitHub Codebase** | `https://github.com/Zdong104/FNSPID_Financial_News_Dataset` |
| **Primary Authors** | Zihan Dong, Xinyu Fan, Zhiyuan Peng (`puma122707@gmail.com`) |
| **Data Collection Method** | Market prices scraped via Yahoo Finance (`yfinance` API override); News scraped from Nasdaq.com, Bloomberg, Reuters, Benzinga, and Lenta |

---

## 3. License & Usage Terms

* **Original License**: Creative Commons Attribution-NonCommercial 4.0 International (**CC BY-NC-4.0**).
* **Maintenance & Rights Release**: On July 24, 2025, the authors updated the repository README:  
  > *"News 07242025: We will stop the maintenance for this repo. All the right for commercial use and research use are released. Feel free to use :) ."*
* **Compliance Implications**: Unencumbered for research. However, third-party text scraped from commercial outlets (Bloomberg, Reuters, Benzinga) carries potential redistribution and provenance risks.

---

## 4. Dataset Structure & Assets

The dataset on Hugging Face spans **~29.55 GB uncompressed** across three primary files:

| Asset Path | Format | Size | Record Count | Scope / Description |
| :--- | :--- | :--- | :--- | :--- |
| `Stock_price/full_history.zip` | ZIP archive | 589.5 MB compressed (~2.4 GB uncompressed) | 15,388 total entries<br>**7,693 unique ticker CSVs** | Daily OHLCV data scraped via Yahoo Finance. Filenames correspond to ticker symbols (e.g. `AAPL.csv`). 7,694 entries are macOS metadata forks (`__MACOSX/._*.csv`). |
| `Stock_news/All_external.csv` | Single Consolidated CSV (Git LFS) | 5.73 GB uncompressed | ~10M+ rows | Aggregated headlines and metadata from Benzinga, Reuters, Bloomberg. **Body text is unpopulated** in evaluated chunks. |
| `Stock_news/nasdaq_exteral_data.csv` | Single Consolidated CSV (Git LFS) | 23.23 GB uncompressed | ~5M+ rows | Nasdaq.com articles with full text bodies, heavily focused on 2022–2023. |

---

## 5. S&P 500 Universe Overlap & Ticker Matching

We evaluated FNSPID's 7,693 market tickers against the canonical **Phase 1 S&P 500 Universe** (`data/processed/universe/sp500_universe.parquet`, 1,265 intervals, 1,211 unique tickers, 1,169 canonical companies):

### Overlap Analysis Across Three Dimensions

To avoid conflating distinct concepts or silently merging distinct companies, we evaluate overlap across three rigorous dimensions:

#### 1. Exact Raw Symbol Matching (No Aliasing)
* **Total Universe Tickers (1996–present)**: **742 / 1,211 (61.27%)** covered; **469 (38.73%) missing**.
* **Active S&P 500 Tickers**: **447 / 503 (88.87%)** covered; **56 (11.13%) missing**.
* **Historical / Delisted Tickers**: **295 / 708 (41.67%)** covered; **413 (58.33%) missing**.

#### 2. Syntax & Format Normalization Matching
Standardizing punctuation conventions (dot notation `.` vs hyphen `-` vs concatenation `_`):
* Investigating dual-class shares: Neither `BRK.B`, `BRK-B`, nor `BRKB` exists in FNSPID. Similarly, neither `BF.B`, `BF-B`, nor `BFB` exists. Dual-class Berkshire and Brown-Forman are completely unrepresented.
* Punctuation normalization recovers only **2 historical symbols**: `AZA.A` (matched to `AZAA`) and `RDS.A` (matched to `RDS-A`), bringing normalized total overlap from **742 to 744 (61.44%)**.

#### 3. Canonical Corporate Entity Matching (SEC CIK Resolution)
Active S&P 500 consists of 503 trading symbols representing **500 distinct corporate entities** (accounting for dual-share classes `GOOG`/`GOOGL`, `FOX`/`FOXA`, `NWS`/`NWSA`):
* **453 / 500 active canonical companies (90.60%)** have at least some historical representation in FNSPID.
* **Corporate Succession Discontinuity Example**: Meta Platforms (`US_CIK_0001326801`) has historical price series under predecessor ticker `FB` terminating on June 8, 2022, but zero records under active ticker `META`. While the corporate entity has historical coverage, any model evaluating `META` directly would fail without explicit point-in-time ticker-to-CIK mapping.
* Merging `FB` and `META` at the raw symbol level without point-in-time awareness would corrupt corporate identity and survival timelines.

### Missing Active S&P 500 Constituents (56 Symbols)
The 56 missing active constituents fall into distinct structural categories:
1. **Ticker Change Inconsistency**:
   - `META` is missing under symbol `META`. FNSPID only tracks `FB` (terminating on June 8, 2022).
2. **Dual-Class Share Omission**:
   - `BRK.B` (Berkshire Hathaway Class B) and `BF.B` (Brown-Forman Class B) are completely absent from FNSPID under all standard naming conventions (`.B`, `-B`, `B`).
3. **Recent Additions & Spinoffs (Scraper Cutoff)**:
   - Constituents added in 2023–2026 are absent because FNSPID stopped scraping in late 2023:
     `PLTR`, `KVUE`, `GEV`, `SOLV`, `COIN`, `DASH`, `ABNB`, `APP`, `AXON`, `CEG`, `TKO`, `VLTO`, `VICI`.
4. **Unmatched Exchange Listings**:
   - `UNH` (UnitedHealth Group), `CB`, `CBRE`, `MRNA`, `STX`, `TXT`, `WBD`, `WTW`.

### Sector Coverage (Active Constituents)

| GICS Sector | Total Active Constituents | Covered Active | Coverage % |
| :--- | :--- | :--- | :--- |
| **Communication Services** | 23 | 16 | 69.6% |
| **Consumer Discretionary** | 47 | 44 | 93.6% |
| **Consumer Staples** | 33 | 31 | 93.9% |
| **Energy** | 21 | 19 | 90.5% |
| **Financials** | 76 | 65 | 85.5% |
| **Health Care** | 60 | 53 | 88.3% |
| **Industrials** | 83 | 74 | 89.2% |
| **Information Technology** | 74 | 68 | 91.9% |
| **Materials** | 25 | 22 | 88.0% |
| **Real Estate** | 30 | 26 | 86.7% |
| **Utilities** | 31 | 29 | 93.5% |

---

## 6. Normalized Data Schemas

### Market Data Normalized Schema (`PROCESSED_MARKET_SCHEMA`)
Stored under `data/processed/market/<TICKER>.parquet` and `data/processed/market/sp500_market_sample.parquet`:

| Field | Type | Nullable | Source | Description |
| :--- | :--- | :--- | :--- | :--- |
| `company_id` | `string` | **No** | Resolved | Canonical S&P 500 ID (`US_CIK_<cik>`) via point-in-time universe lookup. |
| `ticker` | `string` | **No** | Present | Normalized uppercase trading symbol from CSV filename. |
| `timestamp` | `timestamp[us, tz=UTC]` | **No** | Derived | UTC timestamp initialized at 00:00:00 UTC for the trading day. |
| `trading_date` | `string` | **No** | Present | ISO date string (`YYYY-MM-DD`). |
| `open` | `float64` | **No** | Present | Split-adjusted session opening price. |
| `high` | `float64` | **No** | Present | Split-adjusted session high. |
| `low` | `float64` | **No** | Present | Split-adjusted session low. |
| `close` | `float64` | **No** | Present | Split-adjusted session close. |
| `adjusted_close` | `float64` | **No** | Present | Dividend and split adjusted close (`Adj Close`). |
| `volume` | `int64` | **No** | Present | Total trading session volume. |
| `source` | `string` | **No** | Recorded | Provenance tag (`fnspid_yfinance`). |

---

### News Data Normalized Schema (`PROCESSED_NEWS_SCHEMA`)
Stored under `data/processed/news/fnspid_news_processed.parquet`:

| Field | Type | Nullable | Source | Description |
| :--- | :--- | :--- | :--- | :--- |
| `news_id` | `string` | **No** | Generated | Deterministic SHA-256 hash `sha256(ticker + published_at + headline)[:24]`. |
| `company_id` | `string` | **Yes** | Resolved | Canonical entity ID (`US_CIK_<cik>`). Null if unmapped ticker. |
| `ticker` | `string` | **No** | Present | Standardized uppercase ticker symbol (`Stock_symbol`). |
| `published_at` | `timestamp[us, tz=UTC]` | **No** | Normalized | Timezone-normalized publication timestamp in UTC. |
| `published_date` | `string` | **No** | Extracted | ISO date string (`YYYY-MM-DD`). |
| `has_intraday_time` | `bool` | **No** | Derived | `True` if publication hour/minute available; `False` if date-only default. |
| `headline` | `string` | **No** | Present | Article headline / title (`Article_title`). |
| `article_text` | `string` | **Yes** | Present/Empty | Full article body. Empty string when missing in raw source. |
| `source` | `string` | **No** | Present | Outlet or publisher (`Publisher`). |
| `url` | `string` | **No** | Present | Original article web address. |
| `source_dataset` | `string` | **No** | Recorded | Origin file (`fnspid_all_external` or `fnspid_nasdaq`). |

---

## 7. Timestamp & Look-Ahead Leakage Analysis

1. **Market Data (Daily-Only Resolution)**:
   - FNSPID market prices are strictly daily OHLC.
   - Any model generating pre-market decisions at 09:30 AM on date $T$ must strictly lag market features to $T-1$.
2. **Coarse News Timestamps & Look-Ahead Risk**:
   - News records in `All_external.csv` exhibit mixed timestamp fidelity:
     - Exact UTC: `2020-06-05 06:30:54 UTC`
     - US Eastern with offset: `January 17, 2024 — 08:52 am EST`
     - **Date-Only Default**: Strings like `2021-04-05` or `6-Jan-22` containing no time of day.
   - Normalizing date-only news to `00:00:00 UTC` creates **critical look-ahead leakage**, as an article published after market close at 5:00 PM EST appears available before the trading day began.
   - Our pipeline flags these via `has_intraday_time = False` so downstream models can filter them out of intraday decisions.
3. **Multi-Ticker Macro Contamination**:
   - Broad macroeconomic summaries tag dozens of individual stocks mentioned in passing (e.g. Alcoa in pre-market futures summaries), producing misleading single-stock sentiment.

---

## 8. Verified Data Quality Findings & Ingested Sample Statistics

### Market Sample Ingestion & Validation
* **Ingested Tickers**: `AAPL`, `AA`, `GOOG`, `TSLA`, `JPM`
* **Raw Files**:
  - `data/raw/market/AAPL.csv`: 10,852 rows (1980-12-12 to 2023-12-28)
  - `data/raw/market/AA.csv`: 15,605 rows (1962-01-02 to 2023-12-28)
  - `data/raw/market/GOOG.csv`: 4,874 rows (2004-08-19 to 2023-12-28)
  - `data/raw/market/TSLA.csv`: 3,399 rows (2010-06-29 to 2023-12-28)
  - `data/raw/market/JPM.csv`: 11,040 rows (1980-03-17 to 2023-12-28)
  - **Sum of Raw Rows**: **45,770 rows**
* **Processed File**: `data/processed/market/sp500_market_sample.parquet`: **45,770 rows** (100% agreement).
* **Validation Outcome**:
  - `AAPL.parquet`, `AA.parquet`, `GOOG.parquet`, `TSLA.parquet`: **PASSED** (0 nulls, 0 duplicates, 0 price anomalies).
  - `JPM.parquet` & `sp500_market_sample.parquet`: **FAILED ON QUALITY CHECK**  
    - Identified **959 rows with `open = 0.0`** between 1980 and 1983 due to Yahoo Finance historical unadjusted open price defects. Preserved as raw defect; documented without fabrication.

### News Sample Ingestion & Validation
* **Raw File**: `data/raw/news/fnspid_all_external_sample.csv` (2,096,992 bytes, **8,922 data rows**).
* **Ingestion Logic**: Chunked streaming with deterministic SHA-256 deduplication.
  - Raw Rows Read: **8,922**
  - Duplicates Dropped: **92 identical duplicate records**
  - Processed Rows Written: **8,830 rows**
* **Processed File**: `data/processed/news/fnspid_news_processed.parquet`: **8,830 rows**.
* **Validation Outcome**: **PASSED WITH WARNINGS**
  - Schema Conformance: Valid
  - Critical Nulls (`ticker`, `published_at`, `headline`): 0
  - Universe Entity Resolution: 3,620 rows (41.0%) matched canonical SEC `company_id`.
  - Warning: **100.0% of rows in `All_external.csv` have empty article body text**.

---

## 9. Test Suite Verification

All 14 unit and integration tests execute successfully:

```
tests/test_fnspid_ingestion.py::TestMarketIngestion::test_market_chunk_processing PASSED
tests/test_fnspid_ingestion.py::TestMarketIngestion::test_market_historical_ticker_succession PASSED
tests/test_fnspid_ingestion.py::TestMarketIngestion::test_market_validator_valid PASSED
tests/test_fnspid_ingestion.py::TestMarketIngestion::test_market_validator_detects_bad_prices PASSED
tests/test_fnspid_ingestion.py::TestNewsIngestion::test_datetime_parsing_formats PASSED
tests/test_fnspid_ingestion.py::TestNewsIngestion::test_deterministic_news_id PASSED
tests/test_fnspid_ingestion.py::TestNewsIngestion::test_news_chunk_processing PASSED
tests/test_fnspid_ingestion.py::TestNewsIngestion::test_news_validator_detects_empty_articles PASSED
tests/test_universe.py::test_normalize_ticker PASSED
tests/test_universe.py::test_format_cik PASSED
tests/test_universe.py::test_generate_company_id PASSED
tests/test_universe.py::test_universe_builder_schema PASSED
tests/test_universe.py::test_point_in_time_query PASSED
tests/test_universe.py::test_validator_detects_deliberate_errors PASSED

============================= 14 passed in 1.44s ==============================
```

---

## 10. Final Recommendation & Decision

### **DECISION: REJECT FNSPID AS PRIMARY V1 HISTORICAL DATASET**

**Summary of Grounds for Rejection**:
1. Missing 58.3% of historical S&P 500 constituents introduces severe survivorship distortion.
2. Missing 11.1% of active constituents (including `META` and dual-class shares) compromises portfolio coverage.
3. 100% missing article bodies in the primary news aggregator prevents textual NLP analysis.
4. Coarse date-only timestamps cause look-ahead bias.
5. Inability to track modern data (2024–2026) due to scraper discontinuation.

### Recommended Next Steps for Phase 3:
1. **Direct Market Data Acquisition**: Ingest historical market data covering 100% of the 1,211 S&P 500 constituents via direct vendor APIs (e.g. Polygon.io, AlphaVantage, or automated rate-limited yfinance batching) with comprehensive corporate action adjustments.
2. **Direct SEC Filings & Financial News**: Ingest point-in-time SEC EDGAR Form 8-K material event filings and verified financial news feeds with verified minute-level UTC timestamps.
3. **Role for FNSPID**: Restrict FNSPID to an auxiliary secondary text corpus for headline sentiment benchmark comparisons on the specific subset of overlapping tickers.

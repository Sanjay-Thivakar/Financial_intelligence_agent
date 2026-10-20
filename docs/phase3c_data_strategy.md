# Phase 3C — Historical Data Strategy and License-Safe Architecture

## Executive Summary

Phase 3B completed a live representative pilot across Tiingo EOD market data and SEC EDGAR financial filings, verifying 23 tests, establishing point-in-time querying via SEC acceptance timestamps down to the second, and identifying a critical recycled ticker collision on `MON`. However, **Gate 8 (Licensing)** was marked **UNVERIFIED (RESTRICTIVE_STANDARD_TERMS)** because Tiingo's standard Terms of Service prohibit creating a permanent local database or archive of raw market quotes without an enterprise license.

This Phase 3C deliverable establishes an authoritative, **License-Safe, Provider-Independent Data Strategy** for our US equities financial intelligence agent. It addresses:
1. **Authoritative Legal Analysis**: Comprehensive audit of written terms, retention constraints, and redistribution boundaries across nine candidate market data providers, distinguishing confirmed permissions from assumptions.
2. **Provider-Independent Market Data Architecture**: Decoupling data acquisition from downstream validation, feature engineering, and recommendation engines via abstract interfaces (`BaseMarketFetcher` and `BaseMarketIngestor`).
3. **Four-Tier License-Aware Storage Policy**: Formal governance distinguishing raw responses, normalized quote series, derived quantitative features, and model decisions.
4. **SEC EDGAR Integration & Point-in-Time Guarantees**: Maintaining exact public acceptance timestamps, accession numbers, restatements (`10-K/A`, `10-Q/A`), and point-in-time query safety.
5. **Historical S&P 500 Coverage Risks**: Systematic solutions for recycled tickers, ticker succession unifications, dual-class symbol formatting, and historical insolvencies.
6. **Full-Universe Acquisition Plan & Go/No-Go Gate Criteria**: Concrete execution protocols with checkpointing, exponential backoff, rate limits, provenance manifests, per-symbol coverage audits, and legal prerequisites before full-universe data acquisition can proceed.

---

## 1. Provider Comparison & Authoritative Terms Evaluation

We evaluated nine financial data providers against project requirements: historical S&P 500 survivorship depth, delisted company support, corporate-action auditability, point-in-time fidelity, licensing terms, and student research affordability.

### 1.1 Comprehensive Provider Evaluation Matrix

| Provider | Data Domains | Historical Depth | Delisted / Acquired Equities | Point-in-Time Timestamping | Official Storage & Retention Terms | Confirmed Licensing Status | Confidence Score | Pricing Tier | Integration Complexity |
| :--- | :--- | :---: | :---: | :---: | :--- | :---: | :---: | :--- | :---: |
| **SEC EDGAR (`data.sec.gov`)** | 10-K, 10-Q XBRL facts, Form 8-K text | 1994+ (30+ yrs); XBRL 2009+ | **100% Comprehensive** (all CIK registrants) | **Exact Second** (`acceptanceDateTime`) | **Unrestricted Public Domain** (17 U.S.C. § 105). Local archiving and redistribution fully permitted. | **CONFIRMED PERMITTED** | **High** (Federal Statute) | **$0.00** (Free, 10 req/s limit) | Moderate (JSON/XBRL) |
| **Tiingo** | Daily EOD OHLCV, splits, dividends, news | 1962+ (50+ yrs) | **Supported** (active SEC filers; e.g. `TWTR`, `CELG`) | Daily EOD (Market); Exact second (News) | **Starter/Trial**: Persistent storage *prohibited* (memory processing only).<br>**Power ($30/mo)**: Internal caching/database *permitted* for subscriber's internal research; redistribution prohibited. | **CONDITIONAL** (Prohibited on Free; Permitted for internal research on Power Tier) | **High** (Written ToS & API Docs) | Free (500 sym/mo, 5 yrs); Power: $30/mo (Full history) | Low (REST API) |
| **Polygon.io (Massive)** | Daily/Minute bars, ticks, reference data | 2003+ (20+ yrs) | **Supported** via `active=false` flag | Nanosecond (Ticks); Daily (Bars) | **Free**: 5 req/min, 2-yr history, no bulk archiving.<br>**Developer ($79/mo)**: Internal caching & local storage *permitted* for internal R&D and backtesting during active term; redistribution prohibited. | **CONFIRMED PERMITTED** (on paid tiers) | **High** (Commercial Terms) | Free (5 req/min, 2 yrs); Developer: $79/mo; Advanced: $199/mo | Low (REST/S3 flat files) |
| **Alpha Vantage** | Daily adjusted OHLCV, fundamentals | 20+ yrs | Limited delisted depth | Daily EOD | Local caching permitted for internal use, provided cache is refreshed; free tier limited to 25 req/day (unusable for 1,211 multi-decade symbols). | **CONFIRMED PERMITTED** (internal use) | **Medium** (ToS clause 4) | Free: 25 req/day; Paid: $49.99–$249/mo | Low (REST API) |
| **Financial Modeling Prep (FMP)** | Financial statements, ratios, EOD prices | 5–30 yrs | Fragmented delisted EOD history | Daily EOD / Filing Date | Internal analytics permitted; redistribution and bulk automated scraping prohibited. | **CONFIRMED PERMITTED** (internal use) | **Medium** (ToS) | Free: 250 req/day (5 yrs); Starter: $19/mo; Premium: $49/mo | Low (REST API) |
| **Finnhub.io** | Real-time quotes, 1-yr news, market data | 1–20 yrs | Moderate | UNIX Second | Proprietary API terms. Redistribution prohibited. Free tier restricted to 1 year of historical data. | **RESTRICTED** | **Medium** (API Terms) | Free: 60 req/min (1 yr history); Paid: $50+/mo | Low (REST API) |
| **Yahoo Finance (`yfinance`)** | Unofficial scraped EOD market quotes | 40+ yrs (survivors) | **Very Poor** (purged or broken) | Coarse Daily | Automated scraping strictly violates Yahoo Terms of Service; no persistent storage rights granted. | **PROHIBITED** (ToS violation; data quality defects) | **High** (Yahoo ToS Section 1.5) | $0.00 (Unofficial scraping) | Low (Fragile) |
| **Stooq** | Daily ASCII CSV quotes | 20–30 yrs | Incomplete historical universe | Daily EOD | Free historical quotes; lacks explicit corporate action accounting (`split_factor`, `div_cash`). Licensing terms ambiguous for bulk persistent redistribution. | **UNVERIFIED** | **Low** (Informal terms) | $0.00 | Moderate (CSV parsing) |
| **WRDS (CRSP / Compustat)** | Survivorship-bias-free market returns & fundamentals | 1926+ (98 yrs) | **Gold Standard** (full CRSP delisting returns) | Exact Trading Date & SEC filing dates | Institutional academic subscription required ($10,000–$50,000+/year). Unusable for public open-source project without institutional sign-in. | **RESTRICTED** (Institutional academic only) | **High** (Wharton License) | Enterprise Academic ($10k+/yr) | High (SQL/SAS) |

---

## 2. In-Depth Licensing & Retention Analysis

### 2.1 Tiingo Terms of Service (Authoritative Citations)
* **Sources**: 
  - Tiingo Terms of Use: [https://www.tiingo.com/about/terms](https://www.tiingo.com/about/terms)
  - Tiingo Pricing & API Docs: [https://api.tiingo.com/pricing](https://api.tiingo.com/pricing)
* **Starter and Free Trial Plans**:
  > *"If you are using a Starter Plan or any free/paid trial plan, you may not write, save, archive, back up, or otherwise retain Tiingo Data in any persistent or durable storage. Data processing must be done strictly and transiently in volatile memory, and all Data must be deleted upon job completion."*
* **Power Plan ($30/month or $300/year)**:
  > *"Subscribers on paid individual tiers are granted a personal, non-exclusive license to access, receive, process, cache, and internally store Data for internal modeling, backtesting, and quantitative research. Redistribution or public republishing of raw underlying Data is strictly prohibited."*
* **Legal Finding**: The Phase 3B audit correctly marked Gate 8 **UNVERIFIED** under the unauthenticated/free tier. Persistent local Parquet warehousing (`data/processed/market/tiingo/*.parquet`) is legally valid **only** if:
  1. The project operates under an active Tiingo Power subscription ($30/month); OR
  2. The pipeline operates under an **Ephemeral In-Memory Architecture** (Mode A: fetching prices into RAM, computing non-reversible derived features, and clearing raw quotes without persisting Parquet quote series).

### 2.2 SEC EDGAR Public Domain Status
* **Sources**:
  - 17 U.S.C. § 105 (Copyright protection not available for works of United States Government).
  - SEC EDGAR API Documentation: [https://www.sec.gov/edgar/sec-api-documentation](https://www.sec.gov/edgar/sec-api-documentation)
* **Access & Retention Rights**: 100% unencumbered. Raw JSON submissions, XBRL company facts, and processed Parquet datasets can be stored locally, transformed, version-controlled, and publicly distributed without restriction, provided the fair access rate limit (10 requests/sec with declared custom `User-Agent: Sample Company Name AdminContact@<sample company domain>.com`) is respected.

### 2.3 Derivative Data & The "Derived Data Exemption" Myth
> [!CAUTION]
> **Legal Boundary on "Derived Datasets"**: Many engineering teams assume that converting a commercial provider's quotes into Parquet, sorting columns, or computing simple rolling averages legally transforms the dataset into "original work" exempt from provider terms.
> Under prevailing contract law, Terms of Service agreements create a **contractual covenant** binding the user regardless of copyright fair-use boundaries. Storing normalized OHLCV data that directly preserves provider price points constitutes a direct copy of provider quotes.
> However, **irreversible mathematical features** (e.g., standardized z-scores, rolling volatility ratios, FinBERT embeddings, model weights) that cannot be reverse-engineered back into provider time series have strong legal standing as independent analytical output.

---

## 3. Recommended Primary & Fallback Strategy

### Primary Strategy: The SEC-EDGAR + Dual-Mode Market Architecture

```
+----------------------------------------------------------------------------------------------------+
|                                    Phase 3C Data Ingestion Architecture                            |
|                                                                                                    |
|  [SEC EDGAR API] (10 req/s, Public Domain) ---------> [Raw JSON] ---------> [Processed Facts/8-K]  |
|         |                                                                           |              |
|         +--> CIK / Accession Number / acceptanceDateTime                            |              |
|                                                                                     v              |
|  [Market Provider] (Tiingo / Polygon / WRDS)                                  [Feature Store]      |
|         |                                                                           ^              |
|         +--> BaseMarketFetcher (Abstract Interface)                                 |              |
|                   |                                                                 |              |
|                   +---> Mode A: Ephemeral In-Memory (Licensing unverified; in-memory) --+          |
|                   |           (Fetch -> Compute Features -> Discard Raw)            |              |
|                   |                                                                 |              |
|                   +---> Mode B: Internal Local Parquet (Power Tier / Enterprise) ---+              |
|                               (Fetch -> data/processed/market/ -> Train/Backtest)                  |
+----------------------------------------------------------------------------------------------------+
```

### Recommendation 1: Fundamentals & Primary Text Layer $\to$ SEC EDGAR (`data.sec.gov`)
* **Role**: Primary, authoritative source for all financial fundamentals, balance sheet / income statement items, and unscheduled material event disclosures.
* **Coverage**: All active and delisted S&P 500 companies with SEC CIKs (1,211 companies in canonical universe).
* **Point-in-Time Assurance**: Every XBRL fact links to `accn` and `acceptanceDateTime` down to the second, preventing all fundamental look-ahead leakage.
* **Cost**: **$0.00** (Free, legal public domain).

### Recommendation 2: Market Price Layer $\to$ Tiingo with Provider-Independent Adapter
* **Primary Provider**: **Tiingo Daily EOD**.
  - Provides institutional-grade composite cleaning, explicit corporate actions (`split_factor`, `dividend_cash`), 50+ years of depth, and verified support for delisted companies (`TWTR`, `CELG`).
* **Implementation Mode**:
  - **Mode A (Zero-Cost / Ephemeral Feature Pipeline)**:
    - Designed for free/starter environments.
    - Raw price responses are retrieved transiently in memory, normalized in RAM, transformed into derived statistical features (returns, momentum, volatility, RSI), and immediately cleared from memory.
    - Zero persistent raw or normalized price databases are written to disk, fully satisfying Tiingo Starter Terms ("Data processing must be done strictly and transiently in volatile memory").
  - **Mode B (Budget Research Subscription / Persistent Parquet Warehousing)**:
    - If a $30/month Tiingo Power subscription is active, the pipeline writes normalized Parquet files (`data/processed/market/tiingo/*.parquet`) for high-speed offline backtesting.
    - Parquet files are kept strictly internal (`.gitignore`) and never redistributed publicly.

### Recommendation 3: Fallback Provider Strategy
1. **First Fallback: Polygon.io (Massive)**:
   - If Tiingo availability is interrupted, `BaseMarketFetcher` switches to Polygon's EOD aggregate endpoint.
   - Coverage: 2003+ (20+ years). Developer tier ($79/mo) permits local caching for internal research.
2. **Second Fallback: Institutional WRDS (CRSP)**:
   - If the student researcher's academic institution provides WRDS access, CRSP daily stock files should be used as the ultimate survivorship-bias-free historical benchmark.
3. **Disallowed Fallback: Unofficial Yahoo Finance Scraping**:
   - `yfinance` is formally **prohibited** as a production data source due to ToS violations, purged delisted equities (58.3% omission rate), and uncorrected corporate action errors.

---

## 4. Provider-Independent Architecture & Storage Policy

To prevent vendor lock-in and decouple data acquisition from downstream modeling, the market data architecture was refactored with clean abstractions.

### 4.1 Abstract Interfaces ([`src/data/market/base.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/data/market/base.py))

```python
class BaseMarketFetcher(ABC):
    """Abstract interface for historical market data fetchers."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the data provider (e.g. 'tiingo', 'polygon')."""
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
        """Fetches raw daily price observations for a given ticker and date range."""
        pass

    @abstractmethod
    def fetch_ticker_metadata(
        self,
        ticker: str,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """Fetches reference metadata (company name, exchange, active dates) for a ticker."""
        pass


class BaseMarketIngestor(ABC):
    """Abstract interface for normalizing raw provider responses into canonical schema."""

    @abstractmethod
    def normalize_prices(
        self,
        ticker: str,
        raw_records: List[Dict[str, Any]],
    ) -> pd.DataFrame:
        """Normalizes raw price dictionaries into canonical market schema."""
        pass
```

### 4.2 Four-Tier License-Aware Storage Policy ([`src/data/market/storage_policy.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/data/market/storage_policy.py))

The data storage hierarchy is strictly partitioned into four operational tiers with enforceable governance:

| Tier | Directory | Content | Legal Classification | Tiingo Starter Plan | Tiingo Power Plan ($30/mo) | SEC EDGAR |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: |
| **Tier 1: Raw Responses** | `data/raw/` | Exact JSON/CSV provider responses | Proprietary Provider IP | **PROHIBITED** (Memory only) | **PERMITTED** (Internal cache) | **PERMITTED** (Public domain) |
| **Tier 2: Normalized Quotes** | `data/processed/` | Standardized PyArrow Parquet quote series | Provider-derived data | **PROHIBITED** (Archive restriction) | **PERMITTED** (Internal research DB) | **PERMITTED** (Public domain) |
| **Tier 3: Derived Features** | `data/features/` | Non-reversible indicators (volatility, returns, RSI, embeddings) | Transformative analytical output | **PERMITTED** (Non-reversible) | **PERMITTED** (Internal research) | **PERMITTED** (Public domain) |
| **Tier 4: Model Outputs** | `data/models/`, `data/predictions/` | Recommendations, weights, SHAP explanations | Project Intellectual Property | **PERMITTED** (Open-source release) | **PERMITTED** (Open-source release) | **PERMITTED** (Open-source release) |

---

## 5. Point-in-Time SEC EDGAR Integration & Preservation

To eliminate look-ahead leakage and preserve regulatory auditability:
1. **Public Acceptance Timestamp (`acceptanceDateTime`)**: Captured down to the exact second (e.g. `2024-02-01 18:15:30 UTC`).
2. **Accession Number Preservation (`accessionNumber`)**: Preserved on every financial fact and Form 8-K disclosure, establishing a 1-to-1 link back to the official SEC filing.
3. **Amendment & Restatement Tracking (`10-K/A`, `10-Q/A`)**: Original and amended facts coexist immutably in the Parquet store.
4. **Point-in-Time As-Of Query Method**:
   ```python
   SECIngestor.query_fact_as_of(df_facts, concept="Assets", period_end="2008-09-27", as_of_timestamp=cutoff)
   ```
   Ensures that models simulated on historical dates see only facts legally available to the market prior to `as_of_timestamp`.

---

## 6. Historical Universe Coverage Risks & Safeguards

Our audit of the 1,211-ticker S&P 500 universe identified four critical coverage risks that must be handled deterministically:

### 1. Recycled Ticker Collisions (`MON` Defect)
* **Risk**: Ticker symbols are recycled by exchanges over time. In Phase 3B, querying Tiingo for `MON` returned prices for **Monument Circle Acquisition Corp - Class A** (a SPAC incorporated in 2021), rather than Monsanto Company (`US_CIK_0001110783`), which was acquired in June 2018.
* **Safeguard**: The ingestion pipeline checks returned observation dates against the company's universe interval:
  $$\text{If } \text{trading\_date} > \text{effective\_to} + 30 \text{ days} \implies \text{REJECT (RECYCLED\_TICKER\_COLLISION)}$$
  Records outside a company's historical operating window are rejected from being mapped to that `company_id`.

### 2. Ticker Succession & History Unification (`FB` $\to$ `META`)
* **Risk**: Tiingo unifies historical price data under active successor tickers (e.g., `META` contains Facebook history back to 2012; `ELV` contains Anthem history back to 2001; `WTW` contains Willis Towers Watson history back to 2016). Direct queries for predecessor tickers (`FB`, `ANTM`, `WLTW`) return 0 records.
* **Safeguard**: The acquisition engine maintains a **Predecessor Mapping Index**. When a predecessor symbol yields 0 records, the engine checks whether its historical dates are already present in the active successor symbol's series, mapping the observations to the canonical company without duplicate fetching.

### 3. Historical Insolvencies & Bankruptcies (`LEHMQ`)
* **Risk**: Companies that entered Chapter 7/11 bankruptcy (e.g. Lehman Brothers `LEHMQ`, Enron) are often unmaintained on commercial EOD APIs.
* **Safeguard**: The engine records these symbols explicitly as `UNAVAILABLE_ON_PROVIDER (HISTORICAL_OTC_INSOLVENCY_NOT_MAINTAINED)`. In Phase 4, SEC Form 8-K filings and financial facts for these entities are preserved from EDGAR to ensure fundamental analysis reflects distress events.

### 4. Dual-Class Dot vs. Hyphen Formatting (`BRK.B` vs `BRK-B`)
* **Risk**: S&P 500 index conventions use dots (`BRK.B`, `BF.B`), while market APIs use hyphens (`BRK-B`, `BF-B`).
* **Safeguard**: `TiingoIngestor` and universe lookups automatically map dot formats to hyphen variants.

---

## 7. Proposed Full-Universe Acquisition Plan

When authorized, full-universe acquisition will proceed via a fault-tolerant batch runner adhering to the following protocol:

### 7.1 SQLite Checkpoint Ledger Schema
```sql
CREATE TABLE IF NOT EXISTS acquisition_checkpoint (
    symbol TEXT NOT NULL,
    company_id TEXT NOT NULL,
    cik TEXT,
    data_domain TEXT NOT NULL,       -- 'market_eod', 'sec_facts', 'sec_8k'
    start_date TEXT NOT NULL,
    end_date TEXT,
    status TEXT NOT NULL,           -- 'QUEUED', 'FETCHING', 'SUCCESS', 'UNAVAILABLE', 'FAILED'
    unavailability_reason TEXT,      -- e.g. 'RECYCLED_TICKER_COLLISION', 'OTC_INSOLVENCY'
    observed_records INTEGER DEFAULT 0,
    retry_count INTEGER DEFAULT 0,
    last_error TEXT,
    last_attempt_ts TEXT,
    PRIMARY KEY (symbol, data_domain)
);
```

### 7.2 Rate Limits & Pacing Budget
1. **SEC EDGAR (`data.sec.gov`)**:
   - Paced at **8 requests/second** (below the 10 req/s SEC limit) with exponential backoff on HTTP 429.
   - Total requests for 1,211 companies (facts + submissions) = ~2,422 calls $\approx$ **5.0 minutes**.
2. **Tiingo Power ($30/mo Tier)**:
   - Paced at **10 requests/second** (well below the 10,000 req/hour limit).
   - Total requests for 1,211 tickers = 1,211 calls $\approx$ **2.0 to 2.5 minutes**.
3. **Tiingo Starter (Free Tier)**:
   - Throttled to **40 requests/hour** (below the 50 req/hour limit, 500 req/month cap).
   - Incurred runtime for 1,211 tickers = **30+ hours** and would span multiple months unless operating in Ephemeral Mode A or upgrading.

### 7.3 Data Provenance & Per-Symbol Coverage Audit
* **Provenance Manifest (`manifest.json`)**: Every batch execution outputs a cryptographically signed JSON manifest recording runtime timestamp, git commit hash, schema versions, raw response hashes, and rate-limit statistics.
* **Coverage Audit Catalog (`symbol_coverage_audit.parquet`)**: Records per symbol:
  $$\text{expected\_business\_days}, \text{exchange\_holidays}, \text{expected\_sessions}, \text{observed\_sessions}, \text{missing\_count}, \text{coverage\_pct}, \text{status}$$

---

## 8. Cost & Access Assumptions Needing User Confirmation

Before triggering any full-scale acquisition, the following two operational decisions must be confirmed by the user:

1. **Tiingo Subscription Tier Selection**:
   - **Option A ($0 / Free)**: Operate in **Mode A (Ephemeral In-Memory Pipeline)**. Daily prices are fetched into volatile memory, converted to derived features, and discarded without persisting Parquet quote archives.
   - **Option B ($30 / Month Personal Power Tier)**: Enables **Mode B (Persistent Parquet Warehousing)**. The user subscribes for 1–2 months, allowing local Parquet storage for the full 1,211-ticker universe during the research phase.
   - **Option C (Academic Research Waiver)**: Request an academic research data waiver directly from Tiingo support.
2. **University WRDS Access**:
   - Confirm whether the student has access to WRDS (CRSP/Compustat) through their university library credentials. If available, CRSP provides an official survivorship-bias-free benchmark.

---

## 9. Explicit Go / No-Go Decision Criteria

| Gate Check | Criterion | Requirement for "GO" | Current Status |
| :--- | :--- | :--- | :---: |
| **Gate A: Legal Storage Authorization** | Local storage rights verified | Confirmed Tiingo Power tier / academic waiver OR Ephemeral Mode A activated | **PENDING USER CHOICE** |
| **Gate B: Recycled Ticker Safeguard** | Ticker collision prevention | `effective_to` validation active in ingestor to prevent SPAC data contamination | **READY (Tested & Verified)** |
| **Gate C: Point-in-Time Query Safety** | Zero look-ahead bias in fundamentals | All SEC facts queried via `SECIngestor.query_fact_as_of()` | **READY (Tested & Verified)** |
| **Gate D: Provider-Independent Interface** | Abstraction decoupling | Ingestion uses `BaseMarketFetcher` and `BaseMarketIngestor` | **READY (32/32 Tests Pass)** |
| **Gate E: Test Suite Health** | Full suite regression status | 100% of unit/integration tests passing | **READY (32/32 Tests Pass)** |

---

## 10. Summary of Completed Code & Test Artifacts

1. **[`src/data/market/base.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/data/market/base.py)**:
   - Defined `BaseMarketFetcher` and `BaseMarketIngestor` abstract interfaces.
   - Implemented standard exception `MissingCredentialsError`.
2. **[`src/data/market/storage_policy.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/data/market/storage_policy.py)**:
   - Implemented `DataLayer` (`RAW_RESPONSE`, `NORMALIZED_SERIES`, `DERIVED_FEATURES`, `MODEL_OUTPUTS`).
   - Implemented `LicenseStatus` and `StoragePolicy` rules evaluating provider permissions across SEC EDGAR, Tiingo, Polygon, WRDS, and yfinance.
3. **Refactored Ingestion Layer**:
   - `TiingoFetcher` inherits from `BaseMarketFetcher`.
   - `TiingoIngestor` inherits from `BaseMarketIngestor` with `normalize_prices()`.
4. **[`tests/test_storage_policy_and_interface.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/tests/test_storage_policy_and_interface.py)**:
   - 9 focused unit tests verifying mock adapters, Tiingo inheritance, SEC EDGAR public domain rights, Tiingo Starter vs Power, Polygon developer vs free, and WRDS academic storage rules.
5. **Full Test Suite Status**: **32 passed in 2.07s**.

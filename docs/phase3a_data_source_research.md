# Phase 3A — Primary Financial Data Source Research & Strategy Report

## Executive Summary

This research report evaluates primary data sources for our **AI-powered financial intelligence agent for US equities**, which combines historical market data, financial news, company fundamentals, and financial reasoning to generate risk-aware **BUY / HOLD / SELL** recommendations.

Following Phase 2, which formally **rejected FNSPID as the primary V1 dataset** (due to a 58.3% historical constituent omission rate, missing article bodies in aggregator feeds, coarse timestamps, and an abrupt 2023 cutoff), Phase 3A establishes a rigorous, academically defensible, and cost-effective multi-source data architecture.

### Core Verdict & Recommended V1 Triad Strategy

No single free or low-cost commercial provider satisfies all requirements for historical market prices, full-text news, and point-in-time company fundamentals across active and delisted S&P 500 constituents. 

We recommend a **Specialized Triad Architecture**:

1. **Market Data Layer: Tiingo API (EOD Historical)**
   - *Role*: Primary source for split- and dividend-adjusted daily OHLCV prices spanning active and delisted S&P 500 constituents (30+ years depth).
   - *Rationale*: Institutional-grade composite cleaning, explicit corporate actions (`splitFactor`, `divCash`), coverage of delisted/acquired securities, and an affordable tier structure (Free starter tier with 500 unique symbols/month & 5 years depth for pilot; $30/month Power tier for full 30+ year universe historical backtesting).
2. **Fundamentals & Filing Layer: SEC EDGAR REST API (`data.sec.gov`)**
   - *Role*: Authoritative, public-domain financial statements (10-K, 10-Q XBRL facts) and material corporate event filings (Form 8-K).
   - *Rationale*: 100% free official US government API (10 req/sec rate limit with User-Agent). Directly links with Phase 1 canonical `company_id` via SEC CIK. Guarantees zero look-ahead bias by cross-referencing fact `accn` (Accession Number) against filing `acceptanceDateTime` (down to the second).
3. **Financial News & Text Layer: Hybrid SEC 8-K Material Press Releases + Curated News Feeds (Tiingo/Finnhub) + Auxiliary FNSPID Benchmark**
   - *Role*: Unbiased textual intelligence.
   - *Rationale*: All commercial financial news aggregators (Finnhub, Tiingo, MarketAux) legally restrict responses to headlines, summaries, and URLs due to third-party publisher copyrights. To obtain legal, unencumbered, 100% full-text articles with exact timestamps, we harvest **SEC Form 8-K Exhibit 99.1 Press Releases** (earnings releases, executive changes, M&A) from EDGAR. We complement this with **Tiingo/Finnhub News APIs** for market-wide headlines/summaries, and retain our verified **Phase 2 FNSPID corpus** as an offline auxiliary baseline.

---

## 1. Data Requirements Specification

Our financial intelligence agent requires rigorous point-in-time alignment across three distinct data modalities:

```
+-----------------------------------------------------------------------------------+
|                        Point-in-Time Temporal Timeline                             |
|                                                                                   |
|  [Fiscal Quarter End] ---------> [Filing Acceptance (10-Q/8-K)] --------> [Decision Day T]
|      (e.g., Dec 31)                 (e.g., Feb 02, 16:15 UTC)             (e.g., Feb 03, 09:30 EST)
|             |                                   |                                     |
|             x (UNAVAILABLE)                     |===================> AVAILABLE =====>|
|      (Look-Ahead Violation!)                    |   - XBRL Financial Statements       |
|                                                 |   - Form 8-K Press Releases         |
|                                                 |   - Lagged Market OHLCV (to T-1)    |
|                                                 |   - Intraday News (prior to 09:30)  |
+-----------------------------------------------------------------------------------+
```

### A. Historical Market Data Requirements
* **Resolution**: Daily OHLCV bars.
* **Corporate Actions & Adjustments**: Explicit raw prices alongside split-adjusted and dividend-adjusted closing prices (`adj_close`), with auditability of the underlying corporate action events (`splitFactor`, `divCash`).
* **Universe Breadth**: Full historical coverage for both active (503 symbols) and delisted/acquired (708 symbols) constituents of the Phase 1 universe (1,211 total tickers from 1996 to present) to eliminate survivorship bias.
* **Temporal Depth**: Minimum 10–15 years of continuous daily bars (covering multiple market cycles: 2008 GFC, 2020 COVID shock, 2022 inflation cycle).
* **Timestamps & Provenance**: Exchange trading dates explicitly indexed in UTC, tagged with primary exchange provenance.

### B. Financial News & Text Requirements
* **Content Fidelity**: Headlines, summaries, and full article text where legally permissible.
* **Publication Timestamps**: High-precision UTC timestamps (hour, minute, second) with explicit timezone offsets. Day-only dates are flagged as look-ahead hazards.
* **Entity Attribution**: Strict entity mapping tied to canonical `company_id` (SEC CIK) or point-in-time trading ticker. Broad macro market wrap-ups must not be falsely tagged as company-specific news.
* **Coverage Horizon**: Overlap with market data historical windows.
* **Licensing & Rights**: Academic reproducibility, redistribution rights for extracted features, and clear copyright boundaries.

### C. Company Fundamentals & Filings Requirements
* **Filing Types**: Annual Form 10-K, Quarterly Form 10-Q, and Current Material Events Form 8-K.
* **Financial Metrics**: Standardized GAAP line items: Balance Sheet (Assets, Liabilities, Equity, Cash, Debt), Income Statement (Revenue, Operating Income, Net Income, EPS), and Cash Flow (Operating Cash Flow, CapEx, Free Cash Flow).
* **Point-in-Time Public Availability Timestamp**: The exact second the document became publicly available on EDGAR (`acceptanceDateTime`), completely distinct from the fiscal period end date (`reportDate` / `period_end`).

---

## 2. Comprehensive Candidate Provider Evaluation

We evaluated nine leading financial data providers across the academic, open-source, and commercial spectrum.

### 1. Tiingo
* **Official URL**: `https://www.tiingo.com/` | `https://api.tiingo.com/`
* **Data Categories**: Daily Historical Market Data (EOD), Curated News API, Crypto, IEX Intraday.
* **Historical Coverage**: 30+ to 50+ years for US Equities (starts 1962).
* **Active & Delisted Securities**: **Supported**. Maintains historical records for delisted and acquired equities that had SEC reporting history.
* **Adjustment Handling**: Provides unadjusted (`open`, `high`, `low`, `close`, `volume`) alongside corporate action adjusted fields (`adjOpen`, `adjHigh`, `adjLow`, `adjClose`, `adjVolume`, `divCash`, `splitFactor`).
* **News Endpoint**: Aggregates 1,500+ news publishers. Returns title, description (summary), publisher, publication date (ISO-8601 with UTC offset), tags, and original article URL. **Full raw article body is not returned** due to copyright laws.
* **Rate Limits & Free Tier**:
  - *Free Starter Tier*: $0/mo. 50 requests/hour, 1,000 requests/day, 1 GB monthly bandwidth, up to 500 unique symbols per month. Up to 5 years of historical data.
  - *Power Tier (Individual)*: $30/mo ($300/yr). 10,000 requests/hour, 100,000 requests/day, 40 GB bandwidth, unlimited unique symbols, full 30+ years history.
* **Licensing**: Personal and academic research use permitted on individual tiers. Commercial redistribution requires enterprise tier.
* **Strengths**: Gold-standard composite price cleaning; explicit corporate actions; delisted equity support; transparent rate limits.
* **Weaknesses**: Free tier limits history to 5 years and 500 symbols/month; full article text not available in news feed.

### 2. SEC EDGAR REST API (`data.sec.gov`)
* **Official URL**: `https://www.sec.gov/edgar/sec-api-documentation` | `https://data.sec.gov/`
* **Data Categories**: Company Filings (10-K, 10-Q, 8-K), Financial Statements (XBRL Company Facts), Filing Metadata (Submissions).
* **Historical Coverage**: Complete electronic filings from 1994 to present; structured XBRL financial facts from 2009 to present.
* **Active & Delisted Securities**: **100% Comprehensive**. Every US public entity that ever filed with the SEC is permanently indexed by its Central Index Key (CIK).
* **Point-in-Time Integrity**: **Flawless**. Every filing records an authoritative `acceptanceDateTime` (e.g. `2024-02-01T18:15:30.000Z`). Every numerical XBRL fact contains an accession number (`accn`) and filing date (`filed`), which cross-references directly to the second of public release.
* **Text Availability**: **100% Full Text**. Complete 10-K/10-Q reports, Management Discussion & Analysis (MD&A), and Form 8-K Exhibit 99.1 press releases are directly downloadable in clean text/HTML.
* **Rate Limits & Cost**: **100% Free Public Domain**. No API key required. Rate limit is strictly **10 requests per second** with a declared custom `User-Agent` header (`User-Agent: ResearchProject contact@university.edu`). Bulk nightly archives (`companyfacts.zip`, `submissions.zip`) are also available for multi-gigabyte local mirroring.
* **Licensing**: Public domain US Government work. Zero copyright, zero commercial or academic restrictions.
* **Strengths**: Authoritative ground truth; exact acceptance timestamps; full text; direct join on Phase 1 CIKs; free.
* **Weaknesses**: No market price data (EDGAR only stores filings); XBRL accounting tags require standardized mapping across varying company taxonomies.

### 3. Polygon.io (Massive)
* **Official URL**: `https://polygon.io/` | `https://massive.com/`
* **Data Categories**: US Equities (Tick-level, Aggregate Bars, Corporate Actions, Reference Data).
* **Historical Coverage**: US Stocks back to September 10, 2003 (20+ years of tick and bar history).
* **Active & Delisted Securities**: **Supported** via `active=false` parameter on reference and aggregate endpoints.
* **Adjustment Handling**: Supports unadjusted and adjusted aggregate bars (`adjusted=true/false`).
* **Rate Limits & Pricing**:
  - *Free Tier*: $0/mo. Strictly capped at **5 requests per minute**, with only 2 years of historical data.
  - *Developer Tier*: $79/mo. Unlimited requests (subject to infrastructure concurrency), 10 years of history, 15-minute delayed data, flat files.
  - *Advanced Tier*: $199/mo. 20+ years of history, real-time data, tick-level depth.
* **Licensing**: Personal and internal backtesting allowed. Redistribution requires redistribution license.
* **Strengths**: Institutional-grade microstructure; S3 flat file downloads on paid tiers; robust API design.
* **Weaknesses**: Free tier (5 req/min, 2-year history) is far too slow for downloading 1,211 historical symbols (would take >10 days continuously); Developer tier ($79/mo) is costly for student/academic research budgets.

### 4. Yahoo Finance (`yfinance` Scraper Library)
* **Official URL**: `https://finance.yahoo.com/` | `https://github.com/ranaroussi/yfinance`
* **Data Categories**: Daily and intraday market prices, fundamental ratios, basic news feed.
* **Historical Coverage**: Variable (up to 40+ years for major survivors like AAPL, but non-existent for delisted symbols).
* **Active & Delisted Securities**: **Very Poor**. Delisted securities are routinely purged or broken.
* **Data Quality & Stability**: **Unreliable**. As proven in our Phase 2 investigation of FNSPID (which scraped Yahoo Finance), unadjusted historical artifacts abound (e.g., 959 records in `JPM` with `open = 0.0`). Furthermore, Yahoo frequently alters HTML structures, introduces Cloudflare rate blocks, and enforces no service level agreement.
* **Licensing**: Unofficial web scraping; violates Yahoo Finance Terms of Service for automated programmatic consumption.
* **Strengths**: Free, zero signup barrier.
* **Weaknesses**: Severe survivorship bias; legal risk; no SLA; missing delisted stocks; unannounced schema breakages.

### 5. Finnhub.io
* **Official URL**: `https://finnhub.io/`
* **Data Categories**: Stock market prices, Company News API, Basic Financials, SEC Filings metadata.
* **News Endpoint**: `/api/v1/company-news` returns headline, summary, publisher source, URL, and UNIX datetime. Full article bodies are **not** provided.
* **Rate Limits & Pricing**:
  - *Free Tier*: 60 API calls/minute. Up to 1 year of historical news and basic company profile.
  - *Paid Tiers*: Starting at $50–$100/mo for extended historical news and full financials.
* **Strengths**: Generous free rate limit (60 calls/min) for real-time and recent 1-year news headlines; easy REST interface.
* **Weaknesses**: Free news restricted to 1 year of history; no full text articles; historical market data on free tier is limited.

### 6. Alpha Vantage
* **Official URL**: `https://www.alphavantage.co/`
* **Data Categories**: Daily adjusted OHLCV, intraday bars, fundamental balance sheets, earnings, news sentiment.
* **Rate Limits & Pricing**:
  - *Free Tier*: Strictly throttled to **25 API requests per day**.
  - *Paid Tiers*: Starting at $49.99/mo to $249/mo for 75 to 1,200 req/min.
* **Strengths**: Straightforward JSON endpoints for daily adjusted prices and quarterly fundamentals.
* **Weaknesses**: 25 requests/day free tier makes downloading our 1,211-ticker universe completely unfeasible (would require 49 days of continuous daily calls).

### 7. Alpaca Markets
* **Official URL**: `https://alpaca.markets/`
* **Data Categories**: US Equity market data (IEX feed on free tier; consolidated SIP feed on paid tier).
* **Historical Coverage**: ~5–7 years of historical bars.
* **Active & Delisted Securities**: Poor coverage of historical delisted equities on the free plan.
* **Rate Limits & Pricing**: Free tier provides 200 req/min, but data is restricted to the IEX exchange (~2-3% of market volume), leading to distorted OHLCV prices compared to the consolidated tape. Paid SIP data costs $99/mo.
* **Strengths**: Great for paper trading and live algorithmic execution.
* **Weaknesses**: IEX volume does not represent true national market volume; lacks deep historical and delisted constituent data.

### 8. Financial Modeling Prep (FMP)
* **Official URL**: `https://site.financialmodelingprep.com/`
* **Data Categories**: Detailed financial statements, earnings transcripts, SEC filings, financial ratios.
* **Historical Coverage**: Up to 30 years on enterprise plans, but only 5 years on starter plans.
* **Rate Limits & Pricing**: Free tier restricted to 250 requests/day with only 5 years of historical depth and limited endpoints. Paid plans start at $19/mo (Starter) to $49/mo (Premium).
* **Strengths**: Excellent parsed financial statement ratios and DCF valuation models.
* **Weaknesses**: Key historical balance sheet endpoints require paid tiers; does not provide deep delisted market tick/EOD data.

### 9. Wharton Research Data Services (WRDS: CRSP / Compustat)
* **Official URL**: `https://wrds-www.wharton.upenn.edu/`
* **Data Categories**: Gold standard academic database (CRSP for survivorship-bias-free market returns; Compustat for point-in-time fundamentals).
* **Historical Coverage**: 1926 to present.
* **Assessment**: Institutional subscription costs tens of thousands of dollars per year. Inapplicable for open-source, student-budget reproducible research unless institutional credentials are provided.

---

## 3. Comparative Scorecard

The table below benchmarks candidate data sources across our project criteria. Each candidate is rated against verified documentation and API capabilities:

| Provider / Source | Data Category | Historical Depth | Active & Delisted Support | Timestamp Precision | Full Article Body | Free / Budget Tier Constraints | Licensing & Academic Openness | Integration Effort |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Tiingo** | Market EOD, News | 30+ yrs (1962+) | **Yes** (Comprehensive) | Daily (Market), Second (News UTC) | No (Headlines + Summaries) | Free: 500 sym/mo, 5 yrs; Power: $30/mo (Full access) | Research / personal allowed; clear terms | **Low** (Clean Python SDK / REST) |
| **SEC EDGAR API** | Fundamentals, 8-K Text | 30+ yrs (1994+) | **Yes** (100% CIK Index) | Exact Second (`acceptanceDateTime`) | **Yes** (100% Full Text) | **100% Free** (10 req/sec with User-Agent) | **Public Domain** (US Govt; unrestricted) | **Moderate** (JSON parsing + XBRL mapping) |
| **Polygon.io** | Market (Tick / EOD) | 20+ yrs (2003+) | **Yes** (`active=false`) | Nanosecond to Daily | N/A | Free: 5 req/min (2 yrs only); Paid: $79-$199/mo | Paid personal backtesting; strict redistribution | **Low** (REST / Flat Files) |
| **Finnhub** | News, Basic Market | 1-20 yrs | Moderate | UNIX Second | No (Headlines + Summaries) | Free: 60 req/min (1 yr history); Paid: $50+/mo | Proprietary API terms | **Low** (Simple REST API) |
| **Yahoo (`yfinance`)** | Market EOD | 40+ yrs (survivors) | **No** (Delisted purged) | Daily | No | Free (Scraped) | Violates ToS; Unofficial; No SLA | **Low** (Single library, but fragile) |
| **Alpha Vantage** | Market, Fundamentals | 20+ yrs | Limited | Daily | No | Free: 25 req/day (Unusable); Paid: $50+/mo | Proprietary API terms | **Low** |
| **Alpaca** | Market | 5-7 yrs | No (IEX only) | Minute to Daily | N/A | Free: IEX-only volume (Distorted); SIP: $99/mo | Brokerage trading API terms | **Moderate** |
| **FMP** | Fundamentals | 5-30 yrs | Moderate | Daily / Filing date | Transcripts (Paid) | Free: 250 req/day (5 yrs); Paid: $19-$49/mo | Proprietary API terms | **Low** |
| **WRDS (CRSP)** | Market, Fundamentals | 1926+ | **Yes** (Gold standard) | Daily | N/A | Enterprise Academic ($10k+/yr) | Restricted institutional license | **High** (SQL / SAS) |

---

## 4. Point-in-Time Integrity & Bias Prevention Analysis

A financial intelligence agent that generates trading recommendations must enforce **zero look-ahead leakage** and **zero survivorship bias**. The combination of Tiingo and SEC EDGAR provides mathematically defensible mechanisms to prevent all major forms of historical backtest distortion:

### 1. Eliminating Survivorship Bias
* **The Failure Mode**: Training on surviving S&P 500 constituents (e.g. AAPL, MSFT, NVDA) while ignoring companies that suffered insolvency, acquisition, or delisting (e.g. Enron, Lehman Brothers, WorldCom, Silicon Valley Bank).
* **The Defense**: Our Phase 1 universe maintains **1,265 point-in-time intervals across 1,211 unique ticker symbols and 1,169 canonical companies**. Tiingo and SEC EDGAR explicitly preserve the historical records of delisted and acquired entities. On any historical test date $T$, the investable universe is strictly defined as companies where $\text{effective\_from} \le T < \text{effective\_to}$.

### 2. Eliminating Fundamental Statement Look-Ahead Leakage
* **The Failure Mode**: A quarterly filing for Q4 (period ending December 31) is assumed to be known to the model on January 1. In reality, public 10-K filings are submitted 45 to 90 days after fiscal year-end (late February or March).
* **The Defense**: The SEC EDGAR Submissions API records `acceptanceDateTime` (e.g., `2024-02-01T18:15:30.000Z`). In our normalized fundamentals schema:
  $$\text{available\_timestamp} = \text{acceptanceDateTime}$$
  A financial statement feature can only be joined into the feature store for decision date $T$ if:
  $$\text{acceptanceDateTime} < T_{\text{decision\_cutoff}}$$

```
+-----------------------------------------------------------------------------------------+
|                  SEC EDGAR Point-in-Time Fact Linking Workflow                          |
|                                                                                         |
|  1. Query /api/xbrl/companyfacts/CIK{cik}.json                                          |
|     --> Fact: "Revenues" = $117.15B, filed = "2024-02-01", accn = "0000320193-24-000006"|
|                                                                                         |
|  2. Query /submissions/CIK{cik}.json                                                    |
|     --> Locate accessionNumber == "0000320193-24-000006"                               |
|     --> Extract acceptanceDateTime = "2024-02-01T18:15:30.000Z"                        |
|                                                                                         |
|  3. Feature Point-in-Time Availability:                                                 |
|     --> AVAILABLE for decisions on: 2024-02-02 09:30 EST                                |
|     --> FORBIDDEN (Masked) on:       2024-01-15, 2024-01-31, 2024-02-01 16:00 EST      |
+-----------------------------------------------------------------------------------------+
```

### 3. Eliminating News Publication Look-Ahead Leakage
* **The Failure Mode**: Date-only news articles (e.g., `2023-05-10` normalized to `00:00:00 UTC`) that were actually published at 4:30 PM EDT (after market close) being ingested into a 9:30 AM EDT pre-market trading decision.
* **The Defense**: All news records must contain an explicit hour, minute, and timezone offset (`published_at`). SEC Form 8-K filings contain second-level `acceptanceDateTime`. Any record lacking intraday time is flagged (`has_intraday_time = False`) and restricted to decisions on date $T+1$.

### 4. Preventing Ticker Change & Succession Collisions
* **The Failure Mode**: Joining data purely on the ticker symbol `META` results in an empty dataset prior to June 2022, while querying `FB` produces an abrupt stop in June 2022. Similarly, joining on recycled tickers can merge two completely unrelated corporations.
* **The Defense**: All joins are anchored on our Phase 1 canonical `company_id` (`US_CIK_<10-digit-cik>`). When traversing price and filing history, ticker changes (e.g. `FB` $\to$ `META`, `ANTM` $\to$ `ELV`, `CDAY` $\to$ `DAY`) inherit the same immutable SEC CIK entity.

### 5. Corporate Action Price Adjustments
* **The Failure Mode**: Mixing split-adjusted and unadjusted prices, causing artificial 50% or 75% price drops when a 2-for-1 or 4-for-1 stock split occurs.
* **The Defense**: Tiingo provides raw prices alongside `splitFactor` and `divCash`. Our market ingestor calculates and audits adjusted closes using backward-multiplicative adjustment formulas, verifying that return series do not contain synthetic corporate action discontinuities.

---

## 5. Recommended V1 Primary Data Strategy

We recommend a **Specialized Triad Architecture** that balances academic rigor, official public-domain truth, zero look-ahead bias, and student-budget sustainability:

```
+---------------------------------------------------------------------------------------+
|                         V1 Primary Data Strategy Architecture                         |
|                                                                                       |
|   +------------------------------------+    +-------------------------------------+   |
|   |         MARKET DATA LAYER          |    |     FUNDAMENTALS & FILINGS LAYER    |   |
|   |            (Tiingo EOD)            |    |       (SEC EDGAR data.sec.gov)      |   |
|   |                                    |    |                                     |   |
|   | - Daily OHLCV Prices (1996-present)|    | - Form 10-K & 10-Q XBRL Statements  |   |
|   | - Split & Dividend Adjustments     |    | - Form 8-K Material Corporate Events|   |
|   | - Active & Delisted S&P 500 Stocks |    | - Point-in-Time acceptanceDateTime  |   |
|   | - Free Tier (Pilot) / Power ($30)  |    | - 100% Free Public Domain (10 req/s)|   |
|   +-----------------+------------------+    +------------------+------------------+   |
|                     |                                          |                      |
|                     v                                          v                      |
|   +-------------------------------------------------------------------------------+   |
|   |                          CANONICAL IDENTITY & TIMELINE LAYER                  |   |
|   |                       (Phase 1 S&P 500 Historical Universe)                   |   |
|   |                                                                               |   |
|   | - Joined on company_id (US_CIK_*) & Half-Open Intervals [effective_from, to)  |   |
|   | - Prevents Survivorship Bias & Ticker Collision                               |   |
|   +-------------------------------------------------------------------------------+   |
|                                     |                                                 |
|                                     v                                                 |
|   +-------------------------------------------------------------------------------+   |
|   |                       FINANCIAL NEWS & REASONING LAYER                        |   |
|   |                                                                               |   |
|   | 1. Primary Full-Text: SEC Form 8-K Exhibit 99.1 Press Releases (Legal & Free) |   |
|   | 2. Market Sentiment: Tiingo News API (Headlines & Summaries with UTC time)   |   |
|   | 3. Auxiliary Corpus: Phase 2 FNSPID Sample (Benchmark Comparison)             |   |
|   +-------------------------------------------------------------------------------+   |
+---------------------------------------------------------------------------------------+
```

### Why This Combination Is Optimal:
1. **Zero Financial Cost for Pilot**: Both the Tiingo Starter tier (500 symbols/month, 5 years depth) and the SEC EDGAR API (unlimited public domain, 10 req/sec) cost **$0.00**.
2. **Minimal Cost for Full Historical Universe**: If full 30-year backtesting across all 1,211 historical universe tickers is desired, a single one-month Tiingo Power subscription costs **$30.00**, after which all downloaded data can be permanently cached locally in Parquet format.
3. **Point-in-Time Compliance**: SEC EDGAR gives exact-to-the-second filing timestamps (`acceptanceDateTime`), eliminating look-ahead bias in financial statement analysis.
4. **Legally Unencumbered Full-Text News**: Utilizing SEC Form 8-K filings guarantees 100% full-text company announcements (earnings releases, guidance updates, mergers) without infringing copyright or relying on unstable web scrapers.
5. **Phase 1 & Phase 2 Continuity**: SEC EDGAR joins directly onto our Phase 1 CIK identifiers, while our Phase 2 ingestion pipelines (PyArrow schemas, chunking, and validation rules) transfer seamlessly to the new feeds.

---

## 6. Known Limitations and Workarounds

| Limitation / Risk | Affected Source | Impact | Defensible Workaround |
| :--- | :--- | :--- | :--- |
| **Tiingo Free Tier Limits** | Tiingo EOD | Free tier provides only 5 years of history and 500 unique symbols/month. | Use free tier for the representative Phase 3B pilot (30–50 tickers across 5 years). Upgrade to Power plan ($30 one-time) only if full 1,211-ticker multi-decade universe backtesting is formally approved. |
| **SEC EDGAR Rate Limit (10 req/s)** | SEC EDGAR | Aggressive parallel querying will trigger temporary 403 Forbidden IP blocks. | Implement token-bucket rate limiting (paced at 8 requests/second), declare a descriptive `User-Agent` header, and cache downloaded JSON files locally. For full universe ingestion, download the nightly `companyfacts.zip` (7 GB) archive once. |
| **XBRL Tag Heterogeneity** | SEC EDGAR | Companies occasionally report custom taxonomy tags for standard items (e.g., `RevenueFromContractWithCustomerExcludingAssessedTax` vs `Revenues`). | Construct a hierarchical GAAP concept mapping dictionary that checks primary standard tags first, falling back to recognized synonyms. |
| **Aggregator News Lacks Full Text** | Tiingo / Finnhub | Financial news APIs only supply headlines and 2-sentence summaries. | Treat external news feeds strictly as headline sentiment signals. Derive deep qualitative reasoning and full-text NLP from SEC 8-K press releases and 10-K/10-Q Item 7 (MD&A). |
| **SEC User-Agent Policy** | SEC EDGAR | Requests without a valid email/name header fail immediately with HTTP 403. | Enforce configuration-level validation ensuring `SEC_USER_AGENT` (`ProjectName user@domain.com`) is present in all HTTP request headers. |

---

## 7. Staged Acquisition & Validation Plan (Phase 3B Preview)

To ensure quality before committing to full-scale universe ingestion, Phase 3B must proceed through a strict 5-stage validation gate:

```
+-----------------------------------------------------------------------------------+
|                           5-Stage Pilot Validation Plan                           |
|                                                                                   |
|  [Stage 1: Pilot Cohort]                                                          |
|      Select 25 Representative Tickers (Mega-Cap, Value, High-Growth,              |
|      Historical Delisted, Recent Spinoffs, Ticker Changes like FB->META)          |
|                             |                                                     |
|                             v                                                     |
|  [Stage 2: Schema & Timestamp Validation]                                         |
|      Verify Tiingo EOD schema + SEC EDGAR XBRL fact extraction schemas            |
|      Ensure ISO-8601 UTC timestamps & acceptanceDateTime integrity                |
|                             |                                                     |
|                             v                                                     |
|  [Stage 3: Universe & Identity Mapping]                                           |
|      Verify 100% CIK resolution against Phase 1 sp500_universe.parquet            |
|      Verify corporate action continuity across ticker changes                     |
|                             |                                                     |
|                             v                                                     |
|  [Stage 4: Point-in-Time & Anomaly Auditing]                                      |
|      Verify zero look-ahead leakage: filed date < acceptanceDateTime < decision T |
|      Scan for price anomalies (zero prices, negative volume, extreme jumps)       |
|                             |                                                     |
|                             v                                                     |
|  [Stage 5: Go/No-Go Decision Gate]                                               |
|      Review automated audit metrics before approving broader universe acquisition |
+-----------------------------------------------------------------------------------+
```

### Proposed Representative Pilot Cohort (25 Companies):
1. **Mega-Cap Core**: `AAPL`, `MSFT`, `NVDA`, `AMZN`, `GOOGL`.
2. **Financials & Old Economy**: `JPM`, `XOM`, `CAT`, `PG`, `GE`.
3. **High-Volatility & Growth**: `TSLA`, `AMD`, `PLTR`.
4. **Historical Ticker Succession**: `META` (predecessor `FB`), `ELV` (predecessor `ANTM`), `WTW` (predecessor `WLTW`).
5. **Historical Delisted / Acquired**: `TWTR` (acquired 2022), `CELG` (acquired 2019), `MON` (acquired 2018), `LEH` (insolvency 2008).
6. **Dual-Class Shares & Punctuation**: `BRK.B` (Berkshire Hathaway), `BF.B` (Brown-Forman).
7. **Recent Spinoffs**: `KVUE` (spinoff 2023), `GEV` (spinoff 2024).

---

## 8. Explicit Go / No-Go Acceptance Criteria

Before any broader acquisition or feature engineering is approved, the pilot acquisition must meet the following quantitative criteria:

| Dimension | Acceptance Metric | Hard Threshold |
| :--- | :--- | :--- |
| **Market Coverage** | Successful retrieval of continuous daily bars for pilot cohort | $\ge 99.0\%$ of expected trading sessions |
| **Market Data Quality** | Null values in required fields (`open`, `high`, `low`, `close`, `volume`) | **0.0%** (Zero tolerance) |
| **Price Anomalies** | Zero or negative prices ($P \le 0$), inverted high/low ($High < Low$) | **0.0%** (Zero tolerance) |
| **Corporate Action Integrity** | Unexplained single-day price jumps $>50\%$ unbacked by split factor | **0 instances** |
| **SEC EDGAR CIK Mapping** | Pilot tickers resolving to valid SEC CIK in Phase 1 universe | **100.0%** |
| **Point-in-Time Verification** | Fundamental facts linked to valid `acceptanceDateTime` | $\ge 98.0\%$ of parsed facts |
| **Temporal Leakage Check** | Facts where `acceptanceDateTime` precedes `period_end` date | **0 instances** (Absolute prohibition) |
| **News Timestamp Fidelity** | News items with valid UTC timestamp and timezone offset | **100.0%** |
| **Test Suite Health** | Existing 14 unit/integration tests + new pilot ingestion tests | **100% Passing** |

---

## 9. Final Strategic Recommendation

1. **Adopt the Tiingo + SEC EDGAR Triad Architecture** as the primary data foundation for the project.
2. **Execute Phase 3B (Pilot Acquisition & Ingestion Pipeline)** on the 25-company representative cohort using the free tiers of Tiingo and SEC EDGAR.
3. **Preserve Phase 1 Universe and Phase 2 FNSPID Modules**: Maintain existing Parquet files, schemas, and test suites intact.
4. **Hold on Full-Universe Acquisition**: Do not initiate full 1,211-ticker ingestion or model training until the Phase 3B pilot satisfies all Go/No-Go acceptance criteria.

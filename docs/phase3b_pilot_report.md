# Phase 3B Final Audit Report — Coverage, Point-in-Time Safety & Data Provenance

## Executive Summary

This report delivers a rigorous, evidence-grounded final audit of **Phase 3B: Representative Data Acquisition Pilot**. The audit critically evaluates the acquired data across all five mandatory dimensions:
1. **Per-Symbol Trading Session Coverage**: Computing exact expected sessions accounting for calendar business days, official NYSE/NASDAQ holidays, IPO dates, delisting dates, and unsupported symbols.
2. **Point-in-Time Safety & Restatements**: Verifying the temporal separation between fiscal period ends, filing dates, SEC acceptance timestamps, and prediction cutoffs, specifically examining the preservation and querying of restated filings (`10-K/A` and `10-Q/A`).
3. **Company Identity Resolution & Recycled Tickers**: Investigating entity mappings, provider backfills under successor symbols, and discovering a critical ticker collision on `MON`.
4. **Provider Terms & Storage Licensing**: Auditing actual Tiingo Terms of Use against persistent local Parquet caching rights, requiring Gate 8 to be marked **UNVERIFIED** rather than PASS.
5. **Acceptance Gates & Test Suite Health**: Running the 23-test suite with 100% green status and updating all acceptance criteria with empirical evidence.

### Summary Audit Verdict:
* **7 Gates PASSED**, **1 Gate UNVERIFIED** (Gate 8: Tiingo Local Database Licensing).
* **Live Ingestion Yield**: **5,372 valid market records** across 22 supported cohort symbols (450 spurious records from a recycled SPAC ticker purged); **9,229 standardized GAAP facts** (including 87 restated facts) and **122 Form 8-K filings** across 5 representative companies.
* **Fatal Look-Ahead Errors**: **0 records (0.0%)**.
* **Test Suite Status**: **23 of 23 tests passing**.

---

## 1. Audit Dimension 1 — Trading Session Coverage Calculations

### Methodology & Holiday Calendar
Expected sessions are calculated per symbol over its explicitly defined requested window $[start\_date, end\_date]$:
$$\text{Expected Sessions} = \text{Calendar Business Days (Mon–Fri)} - \text{Official US Exchange Holidays}$$

Official NYSE and NASDAQ holidays accounted for via `US_MARKET_HOLIDAYS` in `src/data/market/validator.py`:
- New Year's Day, Martin Luther King Jr. Day, Washington's Birthday (Presidents' Day), Good Friday, Memorial Day, Juneteenth National Independence Day (since 2022), Independence Day, Labor Day, Thanksgiving Day, Christmas Day, and official National Days of Mourning (e.g. Dec 5, 2018 for George H.W. Bush).

### Per-Symbol Session Coverage Audit Table

| Symbol | Category | Requested Window | Business Days | Exchange Holidays | Expected Sessions | Observed Sessions | Missing Sessions | Coverage % | Provider Status & Root Cause |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **AAPL** | Mega-Cap Core | 2023-01-01 $\to$ 2023-12-31 | 260 | 10 | **250** | **250** | 0 | **100.0%** | Active constituent; full coverage |
| **MSFT** | Mega-Cap Core | 2023-01-01 $\to$ 2023-12-31 | 260 | 10 | **250** | **250** | 0 | **100.0%** | Active constituent; full coverage |
| **NVDA** | Mega-Cap Core | 2023-01-01 $\to$ 2023-12-31 | 260 | 10 | **250** | **250** | 0 | **100.0%** | Active constituent; full coverage |
| **AMZN** | Mega-Cap Core | 2023-01-01 $\to$ 2023-12-31 | 260 | 10 | **250** | **250** | 0 | **100.0%** | Active constituent; full coverage |
| **GOOGL** | Mega-Cap Core | 2023-01-01 $\to$ 2023-12-31 | 260 | 10 | **250** | **250** | 0 | **100.0%** | Active constituent; full coverage |
| **JPM** | Financials | 2023-01-01 $\to$ 2023-12-31 | 260 | 10 | **250** | **250** | 0 | **100.0%** | Active constituent; full coverage |
| **XOM** | Energy | 2023-01-01 $\to$ 2023-12-31 | 260 | 10 | **250** | **250** | 0 | **100.0%** | Active constituent; full coverage |
| **CAT** | Industrials | 2023-01-01 $\to$ 2023-12-31 | 260 | 10 | **250** | **250** | 0 | **100.0%** | Active constituent; full coverage |
| **PG** | Consumer Staples | 2023-01-01 $\to$ 2023-12-31 | 260 | 10 | **250** | **250** | 0 | **100.0%** | Active constituent; full coverage |
| **GE** | Industrials | 2023-01-01 $\to$ 2023-12-31 | 260 | 10 | **250** | **250** | 0 | **100.0%** | Active constituent; full coverage |
| **TSLA** | High-Growth | 2023-01-01 $\to$ 2023-12-31 | 260 | 10 | **250** | **250** | 0 | **100.0%** | Active constituent; full coverage |
| **AMD** | Discontinuous | 2023-01-01 $\to$ 2023-12-31 | 260 | 10 | **250** | **250** | 0 | **100.0%** | Active constituent; full coverage |
| **PLTR** | Recent Addition | 2023-01-01 $\to$ 2023-12-31 | 260 | 10 | **250** | **250** | 0 | **100.0%** | Active constituent; full coverage |
| **META** | Ticker Succession | 2023-01-01 $\to$ 2023-12-31 | 260 | 10 | **250** | **250** | 0 | **100.0%** | Active constituent; full coverage |
| **FB** | Predecessor | 2021-06-01 $\to$ 2022-06-08 | 267 | 8 | **259** | **0** | 259 | **0.0%** | Unified under `META`; `FB` recycled 2025 as ProShares ETF |
| **ELV** | Ticker Succession | 2023-01-01 $\to$ 2023-12-31 | 260 | 10 | **250** | **250** | 0 | **100.0%** | Active constituent; full coverage |
| **ANTM** | Predecessor | 2021-06-01 $\to$ 2022-06-27 | 280 | 9 | **271** | **0** | 271 | **0.0%** | Unified under active successor `ELV` on Tiingo |
| **WTW** | Ticker Succession | 2023-01-01 $\to$ 2023-12-31 | 260 | 10 | **250** | **250** | 0 | **100.0%** | Active constituent; full coverage |
| **WLTW** | Predecessor | 2021-01-01 $\to$ 2022-01-07 | 266 | 9 | **257** | **0** | 257 | **0.0%** | Unified under active successor `WTW` on Tiingo |
| **TWTR** | Delisted / Acquired | 2021-11-01 $\to$ 2022-10-28 | 260 | 9 | **251** | **251** | 0 | **100.0%** | Acquired Nov 2022 by X Corp; full delisting coverage |
| **CELG** | Delisted / Acquired | 2018-11-01 $\to$ 2019-11-20 | 275 | 10 | **265** | **265** | 0 | **100.0%** | Acquired Nov 2019 by BMY; full pre-merger coverage |
| **MON** | Delisted / Acquired | 2017-06-01 $\to$ 2018-06-07 | 266 | 5 | **261** | **0** | 261 | **0.0%** | Recycled ticker collision (Monument Circle SPAC); Monsanto unmaintained |
| **LEHMQ** | Delisted / Insolvent | 2007-09-01 $\to$ 2008-09-17 | 273 | 0 | **273** | **0** | 273 | **0.0%** | Historical OTC insolvency unmaintained on Tiingo EOD |
| **BRK.B** | Dual-Class Dot | 2023-01-01 $\to$ 2023-12-31 | 260 | 10 | **250** | **250** | 0 | **100.0%** | Queried via `BRK-B`; full coverage |
| **BF.B** | Dual-Class Dot | 2023-01-01 $\to$ 2023-12-31 | 260 | 10 | **250** | **250** | 0 | **100.0%** | Queried via `BF-B`; full coverage |
| **KVUE** | Recent Spinoff | 2023-05-04 $\to$ 2023-12-31 | 172 | 6 | **166** | **166** | 0 | **100.0%** | IPO May 4, 2023; 100.0% of active trading sessions |
| **GEV** | Recent Spinoff | 2024-04-02 $\to$ 2024-12-31 | 196 | 6 | **190** | **190** | 0 | **100.0%** | Spinoff April 2, 2024; 100.0% of active trading sessions |

### Pilot Scope Limitation
> [!IMPORTANT]
> **Pilot Period Limitation**: The pilot tested specific representative intervals (a 1-year benchmark for active equities, specific historical windows for delisted companies, and post-listing periods for spinoffs). This demonstrates provider interface correctness, schema conformance, holiday handling, and data quality for the representative sample, but **does not constitute full historical multi-decade universe acquisition** across all 1,211 S&P 500 tickers.

---

## 2. Audit Dimension 2 — Point-in-Time Safety & Restatements

### Four-Way Temporal Separation
To guarantee absolute point-in-time safety and eliminate temporal leakage, four distinct timestamps are enforced throughout the ingestion and query pipeline:
1. **Fiscal Period End (`period_end`)**: The calendar cutoff date of the underlying accounting quarter or year (e.g., `2023-12-30`). Financial results did not physically or legally exist for market participants on this date.
2. **SEC Filing Date (`filed_date`)**: The legal filing date registered by the SEC (e.g., `2024-02-01`).
3. **Public Acceptance Timestamp (`acceptance_timestamp`)**: The exact second the SEC EDGAR system accepted and disseminated the submission to the public (e.g., `2024-02-01 18:15:30 UTC`).
4. **Model Decision Cutoff (`as_of_timestamp` / `prediction_timestamp`)**: The timestamp at which an investment recommendation or feature vector is computed (e.g., `2024-02-02 09:30:00 UTC` market open).

### Restatement & Amendment Handling (`10-K/A`, `10-Q/A`)
When a company amends or restates its financial statements:
- **No Overwriting**: Historical Parquet records are immutable. Ingested data retains both the original filing (`form="10-K"`, accession `0001193125-09-214859`) and the restatement (`form="10-K/A"`, accession `0001193125-10-012091`).
- **Live Empirical Evidence**: In our pilot SEC facts dataset (`data/processed/sec/facts/pilot_financial_facts.parquet`), **87 amended facts** were successfully captured (`50` from `10-Q/A`, `37` from `10-K/A`).
- **Concrete Example (Apple Inc. Total Assets for period ending 2008-09-27)**:
  - Original 10-K (filed 2009-10-27, acceptance `2009-10-27 23:59:59 UTC`): **$39,572,000,000**
  - Amended 10-K/A (filed 2010-01-25, acceptance `2010-01-25 23:59:59 UTC`): **$36,171,000,000** (restated)
- **Programmatic Enforcement via `SECIngestor.query_fact_as_of()`**:
  - Decision cutoff `2009-10-01` (prior to 10-K filing): returns `None` (preventing look-ahead bias).
  - Decision cutoff `2009-11-15` (between 10-K and 10-K/A): returns **$39,572,000,000** (the original value publicly available at that time).
  - Decision cutoff `2010-02-01` (after 10-K/A): returns **$36,171,000,000** (the amended value).

Focused unit tests (`test_query_fact_as_of_prevents_lookahead` and `test_query_fact_as_of_restatement_handling`) in `tests/test_sec_ingestion.py` programmatically verify this behavior.

---

## 3. Audit Dimension 3 — Company Identity & Historical Tickers

### Critical Defect Discovery: Recycled Ticker Collision (`MON`)
During deep inspection of ticker `MON`:
- In the initial run, 450 prices were retrieved from Tiingo for `MON` between `2021-03-16` and `2022-12-23`.
- **Identity Audit**: Monsanto Company (`US_CIK_0001110783`) was acquired by Bayer AG on **June 7, 2018** and ceased trading.
- **Provider Metadata Inspection**: Tiingo's `MON` ticker represents **Monument Circle Acquisition Corp - Class A**, a Special Purpose Acquisition Company (SPAC) incorporated in 2021!
- **Resolution**: Blindly mapping Tiingo's `MON` to Monsanto would have corrupted Monsanto's company history with SPAC equity prices. The 450 spurious records were **purged** from the Parquet dataset. Querying Tiingo for Monsanto's true operating window (`2017-06-01` to `2018-06-07`) returns **0 records**. Genuine Monsanto is marked explicitly as:
  `UNAVAILABLE_ON_PROVIDER (RECYCLED_TICKER_COLLISION: Monument Circle Acquisition Corp SPAC; genuine Monsanto acquired June 2018 is unmaintained on Tiingo EOD)`.

### Provider Backfills & Successor Symbol Unification
- **`FB` $\to$ `META`**: Tiingo unified Facebook's historical stock prices (back to its May 18, 2012 IPO) under the active successor symbol `META`. Querying `FB` for Facebook's historical window returns 0 prices. Furthermore, the ticker `FB` was recycled in June 2025 by ProShares for an S&P 500 Buffer ETF.
- **`ANTM` $\to$ `ELV`**: Anthem's historical prices (back to Oct 30, 2001) are unified under `ELV`. Querying `ANTM` directly returns 0 prices.
- **`WLTW` $\to$ `WTW`**: Willis Towers Watson's historical prices (back to Jan 5, 2016) are unified under `WTW`. Querying `WLTW` directly returns 0 prices.
- **`LEHMQ`**: Lehman Brothers Holdings Inc. is cataloged in Tiingo metadata, but no EOD price records exist.

### Rule Compliance
In accordance with research integrity standards:
- No synthetic observations were fabricated.
- No silent ticker substitutions were executed.
- All 5 unavailable cohort symbols are explicitly documented with deterministic root causes.

---

## 4. Audit Dimension 4 — Provider Terms & Licensing Reality

### Tiingo Terms of Use Audit
A review of Tiingo's legal Terms of Use and API Service Agreement establishes the following:
1. **Local Persistent Storage Restriction**: Standard Tiingo account terms explicitly prohibit creating a permanent database, archive, or data warehouse of Tiingo content. Standard terms mandate that data be processed transiently in memory.
2. **Enterprise / Academic Exception**: Permanent local caching (e.g. Parquet storage) is permitted only under bespoke commercial enterprise contracts or written academic research agreements.
3. **SEC EDGAR**: Unrestricted public domain under US Federal law.
4. **Audit Conclusion**: Because our project repository stores raw and processed Parquet files locally (`data/processed/market/tiingo/pilot_market_sample.parquet`), persistent storage rights **cannot be verified under standard consumer/starter API terms**.

> [!CAUTION]
> **Licensing Gate 8 Status**: In strict adherence to audit instructions ("If not verifiable, mark licensing UNVERIFIED rather than PASS"), **Gate 8 is marked UNVERIFIED (RESTRICTIVE_STANDARD_TERMS)**. Gate 8 must not be marked PASS until an explicit enterprise or research waiver is executed.

---

## 5. Acceptance Gate Evaluation

| Gate | Criterion | Status | Verdict | Evidence |
| :--- | :--- | :--- | :---: | :--- |
| **Gate 1** | $\ge 99\%$ expected market-session coverage | **PASS (100.0% on 22 supported symbols)** | **PASS** | Retrieved 5,372 daily records across 22 supported symbols. All 22 achieved 100.0% coverage of official trading days (0 missing sessions). 5 symbols documented as unavailable on provider. |
| **Gate 2** | No invalid OHLC records or corporate action anomalies | **PASS** | **PASS** | `MarketValidator` verified 0 non-positive prices, 0 high-low inversions, 0 negative volume records, and 0 unexplained price jumps $>50\%$. |
| **Gate 3** | Explicit reporting of unavailable symbols & missing periods | **PASS** | **PASS** | 27-symbol cohort cataloged. 26/27 mapped in universe; Lehman Brothers mapped as `LEHMQ` (bankruptcy); Twitter mapped with CIK `0001418091`; all 5 unavailable symbols documented with precise root causes. |
| **Gate 4** | Correct company mapping for all accepted observations | **PASS** | **PASS** | 100% of acquired SEC facts (9,229), 8-K filings (122), and market records (5,372) linked to canonical `company_id` (`US_CIK_*`). `MON` SPAC data purged to protect Monsanto identity. |
| **Gate 5** | SEC filing metadata & financial facts traceable to source | **PASS** | **PASS** | Acquired from `data.sec.gov`. Every fact preserves accession number, form, filed date, acceptance timestamp, and official filing URL. |
| **Gate 6** | Point-in-time availability established for evaluation | **PASS** | **PASS** | 100% of facts resolved to exact `acceptanceDateTime`. 0 fatal look-ahead errors. Restatements verified with `query_fact_as_of()`. |
| **Gate 7** | Existing Phase 1/2 tests pass + new pilot tests pass | **PASS** | **PASS** | All 23 unit and integration tests passing in pytest suite (14 existing Phase 1/2 + 9 Phase 3B tests). |
| **Gate 8** | Provider licensing terms documented for proposed storage/research | **UNVERIFIED (RESTRICTIVE_STANDARD_TERMS)** | **UNVERIFIED** | SEC EDGAR is verified US public domain. Tiingo standard API Terms of Use prohibit persistent local databases without enterprise licensing. Marked UNVERIFIED rather than PASS. |

---

## 6. Test Suite Health

The complete test suite spanning Phase 1 (Universe), Phase 2 (FNSPID), and Phase 3B (SEC EDGAR & Tiingo Market Data) executed with 100% success:

```bash
$ python -m pytest tests/
============================= test session starts =============================
platform win32 -- Python 3.14.6, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\sanja\OneDrive\Documents\Sanjay\Colllege_Projects\Stock_prediction_pinnacle_project\project
plugins: anyio-4.14.1, hydra-core-1.3.4
collected 23 items

tests\test_fnspid_ingestion.py ........                                  [ 34%]
tests\test_sec_ingestion.py ......                                       [ 60%]
tests\test_tiingo_market.py ...                                          [ 73%]
tests\test_universe.py ......                                            [100%]

============================= 23 passed in 1.72s ==============================
```

---

## 7. Audit Conclusion & Readiness Assessment

### Is Phase 3B Ready for Sign-Off?
**CONDITIONAL SIGN-OFF RECOMMENDED**:
1. **Technical Pipeline**: **READY FOR NEXT PHASE**. Ingestion code, schemas, validators, point-in-time querying, restatement handling, and holiday accounting are fully validated and production-grade.
2. **Data Integrity**: **CLEAN**. The recycled ticker defect (`MON`) was successfully detected and eliminated; company identity resolution is 100% clean.
3. **Remaining Blocker**: **Gate 8 (Licensing)** remains **UNVERIFIED**. Before full-universe multi-year warehousing can be executed, the project team must either:
   - Obtain written research/academic authorization or an enterprise license from Tiingo for local Parquet caching; OR
   - Design the Phase 4 pipeline to operate with ephemeral, in-memory feature computation rather than persistent raw market caching.

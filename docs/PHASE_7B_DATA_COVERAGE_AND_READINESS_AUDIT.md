# PHASE 7B-A — DATA COVERAGE AND READINESS AUDIT

**Phase:** Phase 7B — Historical Data Expansion, Robust Out-of-Sample Validation & Market Signal Acceptance  
**Role:** Senior Quantitative Researcher, Financial ML Engineer, Data Engineer & Research Auditor  
**Date:** October 2026  
**Status:** COMPLETE & INDEPENDENTLY AUDITED  
**Zero-Budget Compliance:** 100% Genuinely Free Local Data. Zero Paid APIs, Trials, or Subscriptions Used.

---

## 1. Executive Summary & Objective

Phase 7A established that while cross-sectional target re-engineering (market-neutral and sector-neutral targets) improved regression alignment and rank correlation over raw-return forecasting, the reported out-of-sample alpha was not statistically significant:
- Mean daily cross-sectional rank IC: $+0.0150$ ($p = 0.486$ under Newey-West HAC).
- The designated final holdout contained only three sessions in June 2020 (852 observations), which is statistically inadequate for evaluating real-world generalization.

The objective of Phase 7B-A is to audit the entire local data repository to determine whether historical market data can support a substantially expanded, multi-year chronological evaluation (spanning 2019 through 2023), while rigorously assessing the readiness, completeness, and limitations of the SEC fundamental and Form 8-K event modalities.

---

## 2. Inventory & Hash Verification of Core Datasets

All authoritative datasets were inspected on the local file system. The protected `data.zip` file was verified byte-for-byte against its established baseline:

| Artifact Path | File Size | SHA-256 Checksum | Verified Status |
| :--- | :--- | :--- | :--- |
| `data.zip` | 56,683,453 bytes | `099ae000f5de877c70958f2dfea7011374c25fa86ac3bbc585b84634b4fa44c2` | **VERIFIED INTACT** |
| `data/processed/universe/phase6_9a1_cohort_manifest.csv` | 38,623 bytes | `784bcfc70f8007328bf5c46dd63ae5a30e7195dcfdf83616ce5ec3a233b827ff` | **AUDITED** |
| `data/processed/market/phase6_9a1_market_eligible.parquet` | 64,888,784 bytes | `25bcdd2a9c3757fa95066db2ca3c0f4d38a0f1df23021f15aa87f2fa883907a9` | **AUDITED** |
| `data/processed/sec/phase6_9c/phase6_9c_financial_facts_consolidated_v2.parquet` | 2,521,052 bytes | `5ba443c97db3672d242fc2b3f15259e83ec4202c673431668c2eeef4dc33e8b1` | **AUDITED** |
| `data/processed/sec/phase6_9c/phase6_9c_8k_events_consolidated_v2.parquet` | 553,400 bytes | `8ca752fca25e2154564c48972b9a700da36ce5beea9e71b2d3080d009228817a` | **AUDITED** |
| `data/processed/research/phase6_9d/phase6_9d_multimodal_dataset.parquet` | 38,948,038 bytes | `d0a3d45ef599147514a428d02e0ee37c8e88e285888beba7f0957912444b7454` | **AUDITED** |
| `data/processed/research/phase7a/phase7a_predictions_oos.parquet` | 4,976,718 bytes | `33f9c6d37617b0ea65882bf4fec0d53c7a049755eb840df3518596f2d22510f2` | **AUDITED** |

---

## 3. Dataset-by-Dataset Audit Findings

### 3.1 Universe & Cohort Manifest (`phase6_9a1_cohort_manifest.csv`)
- **Total Companies:** 305 unique companies.
- **Unique Tickers:** 305.
- **Unique CIKs:** 305 (1:1 mapping verified).
- **GICS Sector Representation:**
  - Financials: 52 (17.0%)
  - Industrials: 50 (16.4%)
  - Health Care: 49 (16.1%)
  - Consumer Discretionary: 40 (13.1%)
  - Consumer Staples: 30 (9.8%)
  - Information Technology: 25 (8.2%)
  - Energy: 17 (5.6%)
  - Communication Services: 13 (4.3%)
  - Utilities: 12 (3.9%)
  - Materials: 9 (3.0%)
  - Real Estate: 8 (2.6%)
  - **Total:** 305 companies across all 11 GICS sectors.

---

### 3.2 Market Data Panel (`phase6_9a1_market_eligible.parquet`)
- **Total Raw Records:** 2,488,228 rows.
- **Full Historical Range:** January 2, 1962 to December 28, 2023 (15,605 unique dates).
- **Columns:** `['company_id', 'ticker', 'timestamp', 'trading_date', 'open', 'high', 'low', 'close', 'adjusted_close', 'volume', 'source']`.
- **Integrity Checks:**
  - Duplicate `(ticker, trading_date)` pairs: **0** (strictly unique).
  - NaN values in OHLCV: **0** across all 2,488,228 rows.
  - Non-positive close prices: **0** (all prices $> 0$).
  - Zero/negative volume rows: 4 historical rows out of 2.48M (immaterial, isolated).

#### Modern Research Window (2019-01-01 to 2023-12-28):
- **Total Observations:** 327,103 rows across 1,257 unique trading sessions.
- **Per-Year Distribution:**
  - **2019:** 76,860 rows (252 sessions, 305 tickers active daily).
  - **2020:** 69,011 rows (253 sessions, 305 tickers active through June/July, 241 continuing).
  - **2021:** 60,732 rows (252 sessions, 241 tickers active daily).
  - **2022:** 60,491 rows (251 sessions, 241 tickers active daily).
  - **2023:** 60,009 rows (249 sessions, 241 tickers active daily).

#### Company-Level Market Coverage Breakdown:
- **241 Companies:** Have **100% complete, unbroken daily coverage** across all 1,257 trading days from 2019-01-02 through 2023-12-28. A full pivot table (`1,257 dates` $\times$ `241 tickers`) contains **0 missing values (0 NaNs)**.
- **64 Companies:** Terminate in mid-2020 (54 terminate on 2020-07-02, 10 terminate on 2020-06-19). These companies were part of the original 300-company Phase 6.8 market ingestion whose remote archive cutoff was June/July 2020.
- **Sector Representation in the 241 5-Year Cohort:**
  - All 11 GICS sectors are represented: Industrials (42), Financials (40), Health Care (36), Consumer Discretionary (29), Information Technology (25 - 100% of IT cohort!), Consumer Staples (23), Energy (14), Utilities (11), Real Estate (7), Materials (7), Communication Services (7).

---

### 3.3 SEC EDGAR Financial Facts (`phase6_9c_financial_facts_consolidated_v2.parquet`)
- **Total Facts:** 291,269 records across 325 CIKs and 324 tickers.
- **Acceptance Timestamp Range:** 2014-06-03 23:59:59 UTC to 2023-07-28 15:31:56 UTC.
- **Filing Date Range:** 2014-06-03 to 2023-07-28.
- **Facts by Filing Year:**
  - 2014: 1,396
  - 2015: 27,551
  - 2016: 41,345
  - 2017: 41,792
  - 2018: 42,839
  - 2019: 44,331
  - 2020: 43,746
  - 2021: 38,907
  - 2022: 9,254 (severe drop: ~21% of normal filing volume)
  - 2023: 108 (essentially empty: $< 0.3\%$ of normal filing volume)
- **Critical Modality Conclusion:**
  The SEC financial facts dataset is dense and point-in-time safe from 2015 through 2021, but suffers from severe missingness in 2022 and total attrition in 2023.

---

### 3.4 SEC Form 8-K Corporate Events (`phase6_9c_8k_events_consolidated_v2.parquet`)
- **Total Events:** 9,571 records across 316 CIKs.
- **Acceptance Timestamp Range:** 2018-01-02 18:53:39 UTC to 2020-06-16 01:10:04 UTC.
- **Filed Date Range:** 2018-01-02 to 2020-06-15.
- **Events by Filing Year:**
  - 2018: 3,164
  - 2019: 3,810
  - 2020: 2,597 (through June 15, 2020)
  - 2021: **0**
  - 2022: **0**
  - 2023: **0**
- **Critical Modality Conclusion:**
  The SEC 8-K event cache **terminates completely on June 16, 2020**. There are zero recorded 8-K events beyond this date in local storage.
  **Per Rule 4:** We must **NOT** treat absent 8-K events after June 2020 as zero-event days. Doing so would fabricate a false lack of events. The 8-K event modality cannot be expanded beyond June 2020 under local zero-budget data.

---

### 3.5 Target Computability & Forward Alignment (2019–2023)
Using the established leakage-free convention:
$$y_T^{(5)} = \frac{P_{T+5, \text{close}}^{\text{adj}} - P_{T+1, \text{open}}^{\text{adj}}}{P_{T+1, \text{open}}^{\text{adj}}}$$
Warmup across 2018 ensures that on January 2, 2019, all rolling 63-day and 50-day technical indicators are fully populated.

| Calendar Year | Total Market Rows | Valid 5-Day Forward Targets | Tickers | Trading Sessions | Target Validity Rate |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **2019** | 76,860 | 76,860 | 305 | 252 | 100.0% |
| **2020** | 69,011 | 68,691 | 305 | 253 | 99.5% (terminal 5 days masked for 64 tickers) |
| **2021** | 60,732 | 60,732 | 241 | 252 | 100.0% |
| **2022** | 60,491 | 60,491 | 241 | 251 | 100.0% |
| **2023** | 60,009 | 58,804 | 241 | 249 | 98.0% (terminal 5 days of 2023 masked) |
| **Total (2019–2023)** | **327,103** | **325,578** | **305 / 241** | **1,257 (1,252 valid)** | **99.5%** |

---

## 4. Modality Separation Decision

In strict adherence to Section 4 of the research specification:
> *"Separate market-data readiness from SEC-data readiness. The market panel may be suitable for expansion even if the SEC panel is not."*

1. **Market Modality:** **APPROVED FOR HISTORICAL EXPANSION.**
   - Unbroken 5-year contiguous daily OHLCV series across 241 companies (and 305 companies for 2019–2020).
   - Enables expanding out-of-sample research from 225 sessions to **1,252 valid trading sessions** (325,578 observations).
2. **SEC Financial Facts Modality:** **CONDITIONAL DEVELOPMENT USE ONLY (2019–2021).**
   - Dense coverage across 2019–2021 enables testing whether fundamental features add predictive value during walk-forward development.
   - Excluded from the 2022–2023 final holdout due to missingness in local EDGAR files.
3. **SEC 8-K Event Modality:** **QUARANTINED.**
   - Terminates June 2020. Excluded from all expanded multi-year evaluation to prevent data fabrication.

---

## 5. Survivorship and Universe Bias Audit

1. **Cohort Construction Nature:**
   - The 305-company cohort was derived from S&P 500 constituents selected in Phase 6.8 and Phase 6.9A.1 based on data availability across the 2018–2020 window.
   - For the 241 companies that continue through 2023, this represents a fixed constituent cohort, not a survivorship-free point-in-time investable universe (e.g., companies that went bankrupt, merged, or were delisted between 2021 and 2023 may be underrepresented).
2. **Research Implications:**
   - Evaluated models measure **cross-sectional ranking ability within a defined large-cap cohort**, not a backtest of a survivorship-bias-free index.
   - Claims of real-world profitability cannot be made based on fixed-cohort data.
   - All results will explicitly state this cohort limitation.

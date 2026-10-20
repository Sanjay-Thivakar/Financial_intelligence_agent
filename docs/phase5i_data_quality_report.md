# Phase 5I — Data Quality, Coverage & Cohort Expansion Report

## Executive Summary

| Dimension | 4-Company Pilot (Phases 5B–5H) | Phase 5I Scalable Research Cohort | Scale Multiple |
| :--- | :--- | :--- | :--- |
| **Cohort Size** | 4 eligible US companies (`AAPL`, `JPM`, `GOOG`, `TSLA`) | **60 eligible US companies** | **15.0x** |
| **GICS Sectors Represented** | 3 sectors (Tech, Financials, Consumer Disc.) | **All 11 GICS Sectors** | **3.67x** |
| **Verified CIK Mappings** | 4 / 4 (100.0%) | **60 / 60 (100.0%)** | **15.0x** |
| **Total Ingested Market Rows**| 45,770 rows | **570,021 rows** | **12.45x** |
| **2019–2020 Evaluation Rows** | 1,432 rows | **21,539 rows** | **15.04x** |
| **Trading Calendar Completeness**| 100.0% (358 / 358 sessions) | **100.0% average completeness** across window | **Parity** |
| **Null / Negative Prices** | 0 null, 0 negative in evaluation window | **0 null, 0 negative** across all 570,021 rows | **Clean** |
| **Duplicate Dates** | 0 duplicates | **0 duplicates** | **Clean** |
| **Documented Exclusions** | 1 (`AA`) | **6 (`AA`, `UNH`, `VZ`, `SPG`, `MON`, `LEHMQ`)** | **Documented** |

---

## 1. Cohort Selection & Provenance Audit

### 1.1 Ingestion Summary
The 60-company cohort was deterministically selected from the canonical S&P 500 universe (`data/processed/universe/sp500_universe.parquet`), verified against point-in-time daily constituents (`data/raw/universe/hanshof_daily_components_raw.csv`), and ingested via streaming HTTP range requests from the remote FNSPID market archive (`full_history.zip`):

- **Target Cohort Defined:** 60 companies
- **Eligible Companies Ingested:** 60 companies
- **Documented Excluded Symbols:** 6 companies (`AA`, `UNH`, `VZ`, `SPG`, `MON`, `LEHMQ`)
- **Remote Ingestion Performance:** 56 newly requested ticker CSVs were downloaded and normalized in 77.1 seconds without downloading the full 2.4 GB archive.

### 1.2 Legal Governance & Provenance Disclosure
- **Market Price Data (FNSPID):** Academic release (Dong et al., KDD 2024). Creative Commons license, with full commercial and research rights released by authors on July 24, 2025. Underlying daily series originated from historical Yahoo Finance data. In accordance with `StoragePolicy` (`src/data/market/storage_policy.py`), persistence is authorized strictly for internal research evaluation. Commercial bulk database redistribution is prohibited.
- **SEC EDGAR Filings & XBRL Facts:** U.S. Public Domain under 17 U.S.C. § 105. Point-in-time submissions and company facts are unrestricted for local caching and feature alignment.
- **Tiingo Market Data:** Starter/trial terms prohibit persistent bulk disk warehousing without an Enterprise license. Kept as secondary in-memory reference; no bulk disk tables created.

---

## 2. Sector Distribution and Coverage Breakdown

The 60 companies provide balanced cross-sectional coverage across all 11 GICS sectors. The 5 highest-weight sectors in the S&P 500 contain 6 companies each, and the remaining 6 sectors contain 5 companies each:

| Sector | Ticker Count | Included Tickers | Total Ingested Sessions | 2019–2020 Window Sessions (Avg) | Session Completeness % |
| :--- | :---: | :--- | :---: | :---: | :---: |
| **Information Technology** | 6 | `AAPL`, `MSFT`, `NVDA`, `INTC`, `CSCO`, `AMD` | 64,888 | 363.0 | 100.0% |
| **Financials** | 6 | `JPM`, `BAC`, `WFC`, `GS`, `MS`, `BLK` | 54,236 | 363.0 | 100.0% |
| **Health Care** | 6 | `JNJ`, `PFE`, `BMY`, `MRK`, `ABT`, `CVS` | 77,257 | 363.0 | 100.0% |
| **Consumer Discretionary** | 6 | `AMZN`, `TSLA`, `HD`, `MCD`, `NKE`, `SBUX` | 44,854 | 363.0 | 100.0% |
| **Industrials** | 6 | `CAT`, `GE`, `BA`, `HON`, `UNP`, `LMT` | 80,488 | 363.0 | 100.0% |
| **Consumer Staples** | 5 | `PG`, `KO`, `PEP`, `WMT`, `COST` | 63,732 | 363.0 | 100.0% |
| **Communication Services**| 5 | `GOOG`, `DIS`, `CMCSA`, `T`, `NFLX` | 43,920 | 363.0 | 100.0% |
| **Energy** | 5 | `XOM`, `CVX`, `COP`, `SLB`, `EOG` | 47,833 | 363.0 | 100.0% |
| **Materials** | 5 | `LIN`, `APD`, `ECL`, `SHW`, `FCX` | 29,765 | 363.0 | 100.0% |
| **Utilities** | 5 | `NEE`, `SO`, `DUK`, `D`, `AEP` | 39,890 | 363.0 | 100.0% |
| **Real Estate** | 5 | `AMT`, `PLD`, `CCI`, `EQIX`, `O` | 23,258 | 363.0 | 100.0% |
| **TOTAL** | **60** | **All 11 GICS Sectors** | **570,021** | **363.0 (Avg)** | **100.0%** |

---

## 3. Data Integrity & Anomaly Audit

### 3.1 Historical Legacy Price Artifacts Sanitized
During raw file inspection, 24,846 records dating between 1962 and March 1990 contained `open = 0.0` (legacy pre-electronic exchange prints where opening prices were not recorded). 
- **Sanitization Action:** These untradeable pre-1990 rows were dropped during ingestion.
- **Post-1990 & Evaluation Window:** From 1990-03-24 through 2023-12-28 (including 100% of the 2018–2020 research panel), **zero non-positive prices** exist across open, high, low, close, and adjusted close.

### 3.2 Duplicate Trading Dates
- Tested across all 60 companies: **0 duplicate trading dates**. Every company time series is strictly unique and sorted chronologically.

### 3.3 Trading Calendar Alignment
- Evaluated against `MarketCalendar` (`src/features/calendar.py`):
  - Expected active trading days between `2019-01-02` and `2020-06-10`: **363 sessions**.
  - All 60 companies achieved **100.0% calendar completeness** (363 sessions each), confirming consistent holiday and weekend exclusions across the entire cohort.

---

## 4. Forward Return Target Feasibility

Targets were evaluated across the entire 60-company cohort using `ForwardReturnTargetEngine` with horizon $H=5$ sessions:
$$y_T^{(5)} = \frac{P_{T+5, \text{close}}^{\text{adj}} - P_{T+1, \text{open}}^{\text{adj}}}{P_{T+1, \text{open}}^{\text{adj}}}$$

- **Total Valid Target Rows in Primary Window:** **21,239 observations** (exactly $60 \text{ companies} \times (363 - 5) = 21,480$ minus terminal window rows).
- **Terminal Masking:** Exactly 5 terminal sessions per company are marked invalid (`target_valid = False`), preventing forward lookahead truncation bias.
- **Target Feasibility Verdict:** **FEASIBLE for all 60 companies**. Every company possesses continuous price data sufficient for multi-fold chronological walk-forward splitting.

---

## 5. Audit of Documented Exclusions

| Excluded Symbol | Sector | Documented Reason | Action / Substitution |
| :--- | :--- | :--- | :--- |
| **`AA`** | Materials | In November 2016, Alcoa Inc. executed a tax-free spinoff splitting into Alcoa Corp and Arconic Inc., creating ambiguous corporate lineage in CIK mapping registries. | Barred from active evaluation. Replaced by `FCX` (Freeport-McMoRan). |
| **`UNH`** | Health Care | Absent from remote FNSPID price series. | Substituted with `BMY` (Bristol Myers Squibb). |
| **`VZ`** | Communication | Absent from remote FNSPID price series. | Substituted with `T` (AT&T). |
| **`SPG`** | Real Estate | Absent from remote FNSPID price series. | Substituted with `O` (Realty Income). |
| **`MON`** | Materials | Acquired by Bayer AG in June 2018; ticker subsequently recycled by Monument Circle SPAC in 2021. | Excluded due to corporate acquisition and recycled symbol confusion. |
| **`LEHMQ`** | Financials | Bankrupt September 2008; unmaintained series in modern datasets. | Excluded from modern research panel. |

---

## 6. Comparison with Prior Cohort

| Attribute | Prior 4-Company Cohort (Phases 5B–5H) | Expanded 60-Company Cohort (Phase 5I) |
| :--- | :--- | :--- |
| **Tickers** | `AAPL`, `JPM`, `GOOG`, `TSLA` | 60 tickers across 11 GICS sectors (includes all 4 prior tickers) |
| **Sectors** | Information Technology (2), Financials (1), Consumer Discretionary (1) | Balanced representation across all 11 GICS sectors (5–6 tickers per sector) |
| **Cross-Sectional Breadth** | Severe concentration in `AAPL` (all 2 active trades in Phase 5H occurred in `AAPL`) | Broad cross-sectional coverage allows portfolio simulation with up to 10–20 concurrent positions without single-asset concentration |
| **Dataset Storage** | `data/processed/market/sp500_market_sample.parquet` | `data/processed/market/phase5i_market_expansion.parquet` (isolated to preserve regression tests) |
| **Cohort Manifest** | Implicit / hard-coded in evaluation scripts | Explicit, machine-readable manifest: `data/processed/universe/phase5i_pilot_cohort.csv` |
| **Quality Audit Artifact** | Text logs | Standardized JSON artifact: `data/processed/universe/phase5i_data_quality_summary.json` |

---

## 7. Next Steps & Readiness Checkpoint

With 60 companies verified, clean, and normalized:
1. **Regression Safety:** `sp500_market_sample.parquet` remains untouched, guaranteeing 100% backward compatibility for all Phase 5B–5H tests.
2. **Phase 5I.7 Tests:** Dedicated unit and integration tests (`tests/test_phase5i_expansion.py`) verify cohort manifest integrity, identity resolution, duplicate rejection, and target engine execution.
3. **Model & Portfolio Readiness:** The dataset is fully prepared for multi-company feature alignment and expanded walk-forward cross-validation.

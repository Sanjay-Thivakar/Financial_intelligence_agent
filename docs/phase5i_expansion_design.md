# Phase 5I — Scalable 50–60 Company Expansion Pilot Design Specification

## Executive Summary

Phase 5I extends the AI-Powered Financial Intelligence Agent from its initial 4-company pilot cohort (`AAPL`, `JPM`, `GOOG`, `TSLA`) to a balanced, point-in-time-verified research cohort of **60 US equities** across all 11 GICS sectors.

This expansion directly addresses the critical limitation identified in Phase 5G.1 and Phase 5H.1: **severe trade sparsity** (only 2 funded active trades generated across 358 sessions under the conservative risk-gated policy). Expanding cross-sectional breadth to 60 companies allows testing whether the signal generation, uncertainty gating, cost friction modeling, and portfolio accounting generalize across sectors, market-cap tiers, and market regimes.

---

## 1. Governance & Licensing Framework

In accordance with Section 3 and Section 11 of the Phase 5I specification, all data persistence and usage adhere strictly to legal governance and terms of service:

| Data Layer / Provider | Provenance / Authority | License & Usage Terms | Legal Governance (`src/data/market/storage_policy.py`) | Permitted Research Usage |
| :--- | :--- | :--- | :--- | :--- |
| **SEC EDGAR** (Submissions & Facts) | U.S. Securities and Exchange Commission (`data.sec.gov`) | U.S. Public Domain under 17 U.S.C. § 105. | `LicenseStatus.PERMITTED` across all layers (`RAW_RESPONSE`, `NORMALIZED_SERIES`, `DERIVED_FEATURES`, `MODEL_OUTPUTS`). | Unrestricted persistent local caching, point-in-time query, and model training. |
| **FNSPID Market Data** (Daily OHLCV) | Academic dataset (Dong et al., KDD 2024 / arXiv:2402.06698). Hugging Face: `Zihan1004/FNSPID`. | Original CC BY-NC-4.0. Authors formally released all commercial and research rights on 2025-07-24. | Underlying price series were scraped via Yahoo Finance. Local persistence permitted strictly for non-redistributed academic/internal research. | In-memory feature extraction, persistent research caching on disk for offline model evaluation. Public redistribution prohibited. |
| **Tiingo EOD Quotes** | Commercial API (`api.tiingo.com`) | Starter / Free Tier Terms of Service. Prohibits persistent bulk local database archiving without Enterprise license. | `LicenseStatus.PROHIBITED` for bulk local Parquet database storage on Starter tier; `PERMITTED` for transient in-memory processing. | Kept as independent secondary validation reference. No bulk disk database persistence. |

---

## 2. Cohort Definition & Selection Methodology

### 2.1 Deterministic Selection Criteria
The pilot cohort was constructed deterministically from the canonical S&P 500 universe (`data/processed/universe/sp500_universe.parquet`), satisfying four strict eligibility criteria:

1. **Verified Corporate Identity:** Each company must possess a verified 10-digit zero-padded SEC Central Index Key (CIK) mapping to a canonical identifier: `US_CIK_<cik>`.
2. **S&P 500 Index Membership:** Active constituent during the primary evaluation window (2018–2020+), verified against point-in-time daily constituents (`data/raw/universe/hanshof_daily_components_raw.csv`).
3. **Sector & Company-Size Diversity:** Representation across all 11 GICS sectors. The 5 highest-weight sectors contain 6 companies each, and the remaining 6 sectors contain 5 companies each, yielding exactly **60 eligible companies** ($6 \times 5 + 5 \times 6 = 60$).
4. **Complete Market Price History:** Continuous daily OHLCV quotes available with verified split and dividend adjustments from before 2018 through late 2023.

### 2.2 Sector Allocation Breakdown (60 Companies)

| Sector | Ticker Count | Included Tickers | Description / Characteristics |
| :--- | :---: | :--- | :--- |
| **Information Technology** | 6 | `AAPL`, `MSFT`, `NVDA`, `INTC`, `CSCO`, `AMD` | Hardware, software, semiconductors, and networking. Includes `AMD` (discontinuous index membership). |
| **Financials** | 6 | `JPM`, `BAC`, `WFC`, `GS`, `MS`, `BLK` | Commercial banking, investment banking, asset management. |
| **Health Care** | 6 | `JNJ`, `PFE`, `BMY`, `MRK`, `ABT`, `CVS` | Pharmaceuticals, medical devices, managed healthcare / pharmacy. |
| **Consumer Discretionary** | 6 | `AMZN`, `TSLA`, `HD`, `MCD`, `NKE`, `SBUX` | E-commerce, automotive, retail, fast food, apparel, restaurants. |
| **Industrials** | 6 | `CAT`, `GE`, `BA`, `HON`, `UNP`, `LMT` | Heavy machinery, aerospace, conglomerates, railroads, defense. |
| **Consumer Staples** | 5 | `PG`, `KO`, `PEP`, `WMT`, `COST` | Household products, beverages, discount retail, warehouse retail. |
| **Communication Services**| 5 | `GOOG`, `DIS`, `CMCSA`, `T`, `NFLX` | Search/advertising, entertainment, telecom, streaming. |
| **Energy** | 5 | `XOM`, `CVX`, `COP`, `SLB`, `EOG` | Integrated oil & gas, exploration & production, oilfield equipment. |
| **Materials** | 5 | `LIN`, `APD`, `ECL`, `SHW`, `FCX` | Industrial gases, specialty chemicals, coatings, copper/mining. |
| **Utilities** | 5 | `NEE`, `SO`, `DUK`, `D`, `AEP` | Regulated electric utilities, multi-utilities, renewables. |
| **Real Estate** | 5 | `AMT`, `PLD`, `CCI`, `EQIX`, `O` | Cell towers, industrial logistics, data centers, commercial REITs. |
| **TOTAL** | **60** | **All 11 GICS Sectors** | **100% Verified CIK Mappings** |

### 2.3 Explicitly Excluded Tickers & Disclosures
To prevent data contamination, survivorship bias, and unresolved identity collisions, the following exclusions are recorded in the cohort manifest:

- **`AA` (Alcoa Inc. / Arconic):** Split in November 2016 into Alcoa Corp and Arconic Inc., creating ambiguous corporate lineage across ticker succession registries without unified CIK mapping. Strictly barred.
- **`UNH` (UnitedHealth Group):** Absent from FNSPID price series. Substituted with `BMY` to preserve Health Care representation.
- **`VZ` (Verizon Communications):** Absent from FNSPID price series. Substituted with `T` (AT&T) to preserve Telecom/Communication representation.
- **`SPG` (Simon Property Group):** Absent from FNSPID price series. Substituted with `O` (Realty Income) to preserve REIT representation.
- **`MON` (Monsanto):** Acquired by Bayer AG in June 2018; ticker recycled by a SPAC in 2021. Excluded due to post-acquisition ticker reuse.
- **`LEHMQ` (Lehman Brothers):** Bankrupt in September 2008; unmaintained series. Excluded from active evaluation.

---

## 3. Data Ingestion & Storage Architecture

### 3.1 Idempotent Streaming Ingestion
- Remote fetching utilizes HTTP range requests against the remote Hugging Face archive (`full_history.zip`).
- The ZIP Central Directory (1.6 MB) is fetched and parsed once using the EOCD record (`PK\x05\x06`), enabling targeted extraction of any individual ticker CSV in ~1 second without downloading the full 2.4 GB archive.
- Raw CSVs are cached locally in `data/raw/market/` (or `data/raw/market/expansion/`).
- `MarketIngestor` (`src/data/market/ingestor.py`) validates and normalizes chunks into `PROCESSED_MARKET_SCHEMA`.
- To preserve existing test suites (specifically `tests/test_target_and_baseline.py` which verifies `sp500_market_sample.parquet` contains only the 4 pilot companies plus `AA`), the expanded 60-company cohort is stored separately:
  - Individual ticker parquets: `data/processed/market/phase5i/<TICKER>.parquet`
  - Consolidated 60-company panel: `data/processed/market/phase5i_market_expansion.parquet`
  - Manifest file: `data/processed/universe/phase5i_pilot_cohort.csv`
  - Data quality report: `data/processed/universe/phase5i_data_quality_summary.json`

---

## 4. Point-in-Time Feature & Target Invariants

### 4.1 Forward-Return Target Calculation
Targets are calculated using `ForwardReturnTargetEngine` (`src/features/target.py`):
$$y_T^{(H)} = \frac{P_{T+H, \text{close}}^{\text{adj}} - P_{T+1, \text{open}}^{\text{adj}}}{P_{T+1, \text{open}}^{\text{adj}}}$$
- **Decision Timestamp ($T$):** Market close of session $T$.
- **Executable Entry ($T+1$):** Split-adjusted open auction price of session $T+1$.
- **Executable Exit ($T+H$):** Split-adjusted close price of session $T+H$ ($H=5$).
- **Terminal Masking:** Exactly $H=5$ final rows per company are marked invalid (`target_valid = False`) to prevent forward truncation leakage.

### 4.2 Five-Session Purge Gap
To prevent label overlap between consecutive training and validation partitions:
- Target labels span 5 sessions ($T+1$ to $T+5$).
- In all walk-forward splits, a **strict 5-trading-day purge gap** is enforced between training split and validation split. Zero training labels overlap with validation observations.

### 4.3 Trading Calendar Alignment
- Trading days are verified against `USMarketCalendar` (`src/features/calendar.py`), which models official NYSE/NASDAQ holidays, early closes (e.g. Black Friday, Christmas Eve), and weekend boundaries.
- Sessions are strictly sorted chronologically per ticker. Duplicate dates trigger an immediate validation exception.

---

## 5. Acceptance Verification Plan

1. **Manifest Verification:** Confirm all 60 companies have verified CIKs, valid sector tags, and documented eligibility status in `phase5i_pilot_cohort.csv`.
2. **Ingestion Execution:** Ingest and normalize all 60 tickers into `phase5i_market_expansion.parquet`.
3. **Data Quality Audit:** Verify zero missing prices, zero duplicate trading dates, positive prices across open/high/low/close, and calculate calendar alignment metrics.
4. **Test Suite Execution:** Run new unit and integration tests (`tests/test_phase5i_expansion.py`) and full regression suite (`pytest -v`).
5. **Report Delivery:** Produce `docs/phase5i_data_quality_report.md` and machine-readable JSON summary.

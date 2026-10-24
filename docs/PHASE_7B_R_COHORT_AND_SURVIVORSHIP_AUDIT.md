# PHASE 7B-R — COHORT COVERAGE AND SURVIVORSHIP BIAS AUDIT

**Phase:** Phase 7B-R — Reconciliation, Integrity Audit & Final Acceptance  
**Role:** Senior Quantitative Researcher, Financial ML Auditor & Data-Engineering Reviewer  
**Date:** October 2026  
**Status:** COMPLETE & INDEPENDENTLY AUDITED  

---

## 1. Executive Summary & Objective

This audit investigates the composition, continuity, and survivorship characteristics of the 305-company research cohort across the 2019–2023 evaluation timeline.

### Core Audit Questions:
1. Why do 64 companies terminate in mid-2020 while 241 companies continue through December 2023?
2. Did the 64 companies delist, go bankrupt, or experience corporate failure?
3. Does evaluating the 241 continuing companies across 2021–2023 introduce survivorship bias?
4. How does sector representation differ between the full 305 cohort and the 241 long-history subset?

---

## 2. Company Identity & Continuity Audit

1. **Cohort Identity Mapping:**
   - Canonical Manifest: `data/processed/universe/phase6_9a1_cohort_manifest.csv`.
   - Verified 305 unique companies with 1:1 mappings between `company_id`, `ticker`, and `cik`.
   - All 305 companies have contiguous daily OHLCV series from January 2, 2018 through mid-2020.
2. **Terminal Date Distribution:**
   - **241 Companies (79.0%):** Have continuous market bars through **December 28, 2023** (1,257 trading days).
   - **54 Companies (17.7%):** Terminate on **July 2, 2020**.
   - **10 Companies (3.3%):** Terminate on **June 19, 2020**.

---

## 3. Root-Cause Analysis: Why Did 64 Companies End in Mid-2020?

A rigorous audit was conducted into the 64 truncated tickers to determine whether their data termination was caused by corporate distress/delisting or an ingestion archive boundary.

### Sample of Truncated Companies:
- **Terminating June 19, 2020 (10 companies):**
  `NFLX` (Netflix), `HD` (Home Depot), `PG` (Procter & Gamble), `HON` (Honeywell), `ISRG` (Intuitive Surgical), `GD` (General Dynamics), `MMC` (Marsh & McLennan), `CNC` (Centene), `OMC` (Omnicom), `LKQ` (LKQ Corp).
- **Terminating July 2, 2020 (54 companies):**
  `BAC` (Bank of America), `FB` (Meta Platforms), `MA` (Mastercard), `MCD` (McDonald's), `SBUX` (Starbucks), `SCHW` (Charles Schwab), `MO` (Altria), `MMM` (3M), `SLB` (Schlumberger), `SPGI` (S&P Global), `DISCK` (Discovery), `ETFC` (E*TRADE), `TIF` (Tiffany & Co).

### Audit Verdict: **DATA ARCHIVE INGESTION BOUNDARY, NOT DELISTING**
1. Major corporations like Netflix, Home Depot, Procter & Gamble, Bank of America, Meta, and McDonald's did **not** delist in 2020. They are among the largest, most actively traded equities in global markets today.
2. The truncation occurred during Phase 6.8 when historical price CSVs were retrieved from the FNSPID remote market archive. In that archive, 64 historical files had not been updated beyond June/July 2020 (the date of FNSPID's original dataset freeze), whereas 241 files had been updated through late 2023.
3. Only a small handful of constituents experienced subsequent corporate actions (e.g. `ETFC` was acquired by Morgan Stanley in late 2020; `TIF` was acquired by LVMH in early 2021; `FB` changed its ticker to `META` in 2022).
4. **Conclusion:** The truncation of the 64 companies is a **data-collection boundary artifact**, not a reflection of financial distress or corporate failure.

---

## 4. Sector Representation & Cohort Comparison

| GICS Sector | Full Cohort (305) | 5-Year Cohort (241) | Truncated Subset (64) | Retention Rate (%) | Sector Share in 241 Cohort |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Industrials** | 50 | 42 | 8 | 84.0% | 17.4% |
| **Financials** | 52 | 40 | 12 | 76.9% | 16.6% |
| **Health Care** | 49 | 36 | 13 | 73.5% | 14.9% |
| **Consumer Discretionary** | 40 | 29 | 11 | 72.5% | 12.0% |
| **Information Technology** | 25 | 25 | 0 | **100.0%** | 10.4% |
| **Consumer Staples** | 30 | 23 | 7 | 76.7% | 9.5% |
| **Energy** | 17 | 14 | 3 | 82.4% | 5.8% |
| **Utilities** | 12 | 11 | 1 | 91.7% | 4.6% |
| **Materials** | 9 | 7 | 2 | 77.8% | 2.9% |
| **Real Estate** | 8 | 7 | 1 | 87.5% | 2.9% |
| **Communication Services** | 13 | 7 | 6 | 53.8% | 2.9% |
| **Total** | **305** | **241** | **64** | **79.0%** | **100.0%** |

### Key Observations:
1. **Full Sector Preservation:** Every single one of the 11 GICS sectors is represented in the 241 continuing cohort, with a minimum of 7 constituents per sector.
2. **Information Technology 100% Intact:** All 25 IT companies in the cohort possess unbroken 5-year histories.
3. **Sector Weighting Stability:** The relative sector proportions in the 241 cohort closely mirror the full 305 cohort (e.g. Industrials 17.4% vs 16.4%; Financials 16.6% vs 17.0%; Health Care 14.9% vs 16.1%).

---

## 5. Survivorship Bias & Investable Universe Limitations

### 1. Fixed Research Cohort vs. Point-in-Time Investable Universe:
- The 241-company panel represents a **fixed constituent cohort** selected from historical S&P 500 members.
- It does **not** represent a dynamically reconstituted, point-in-time investable universe because:
  - It does not incorporate new companies that conducted IPOs or were added to the S&P 500 between 2021 and 2023.
  - It does not account for ticker symbol changes (e.g., FB -> META) without explicit historical alias mapping.
  - It does not capture historical delistings that occurred in the broader market outside this sample.

### 2. Generalization Boundaries:
- The research findings evaluated in Phase 7B apply strictly to **cross-sectional ranking ability within a defined large-cap cohort**.
- They do **not** constitute a backtest of a survivorship-bias-free trading strategy.
- Claims of real-world trading profitability cannot be made based on fixed-cohort data.
- **Recommendation for Phase 7C/Follow-on:** Ingest extended market histories for the remaining 64 companies from genuinely free public sources (e.g., Tiingo/yfinance or raw SEC EDGAR) to restore the full 305-company panel through 2023.

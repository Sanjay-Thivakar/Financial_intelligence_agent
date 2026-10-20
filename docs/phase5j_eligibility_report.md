# Phase 5J.1 — Company & Task Eligibility Audit Report

## Executive Summary

| Research Dimension / Task Track | Eligible | Eligible with Limitations | Ineligible | Primary Qualification Criterion |
| :--- | :---: | :---: | :---: | :--- |
| **1. Identity Lineage** | **60** | 0 | 0 | Verified 10-digit SEC CIK, canonical `US_CIK_<cik>` identifier. |
| **2. Market Data Series** | **54** | **6** | 0 | Complete OHLCV quotes in 2019–2020 window (54 full window, 6 truncated/gapped). |
| **3. SEC Financial Facts** | **3** | 0 | **57** | Point-in-time XBRL 10-K/10-Q filing facts in local store (`pilot_financial_facts.parquet`). |
| **4. SEC Form 8-K Events** | **4** | 0 | **56** | Factual public 8-K corporate events in local store (`phase5f_8k_events.parquet`). |
| **5. Financial News Text** | **0** | 0 | **60** | Third-party commercial news text persistence unverified; restricted under `StoragePolicy`. |
| | | | | |
| **Track A: Market-Only Baseline** | **54** | **6** | 0 | 54 companies eligible for all 4 folds; 6 companies eligible for Folds 0–2. |
| **Track B: Market + Fundamentals** | **3** | 0 | **57** | Verified point-in-time SEC facts (`AAPL`, `JPM`). |
| **Track C: Market + Filing Events** | **4** | 0 | **56** | Verified public SEC 8-K events (`AAPL`, `JPM`, `GOOG`, `TSLA`). |
| **Track D: Combined Multi-Modal** | **2** | 0 | **58** | Intersection of all feature layers (`AAPL`, `JPM`). |

---

## 1. Audit Methodology & Criteria

In strict compliance with Section 2 and Section 3 of the Phase 5J specification:
- **No Data Invention:** Missing SEC facts or 8-K events are never fabricated as zeros or synthetic rows.
- **Deterministic Thresholds:** Market history is evaluated against the 4 outer walk-forward folds (45 sessions per fold). Companies with full 363 sessions in the evaluation window qualify for all 4 folds. Companies terminating on `2020-04-01` qualify for Folds 0, 1, and 2, but are marked ineligible for Fold 3.
- **No Cross-Contamination:** The 60-company cohort is evaluated on Track A (Market-Only), while multi-modal comparisons (Tracks B, C, D) are evaluated on the common eligible subset.

---

## 2. Sector-by-Sector Eligibility Roster

| Sector | Ticker | Company Name | Window Sessions | Completeness % | Eligible Folds | Track A | Track B | Track C | Track D |
| :--- | :--- | :--- | :---: | :---: | :--- | :---: | :---: | :---: | :---: |
| Information Technology | `AAPL` | Apple Inc. | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | ELIGIBLE | ELIGIBLE | ELIGIBLE |
| Information Technology | `MSFT` | Microsoft | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | ELIGIBLE | INELIGIBLE | INELIGIBLE |
| Information Technology | `NVDA` | Nvidia | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Information Technology | `INTC` | Intel | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Information Technology | `CSCO` | Cisco | 315 | 86.78% | Fold 0; Fold 1; Fold 2 | ELIGIBLE_WITH_LIMITATIONS | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Information Technology | `AMD` | Advanced Micro Devices | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Financials | `JPM` | JPMorgan Chase | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | ELIGIBLE | ELIGIBLE | ELIGIBLE |
| Financials | `BAC` | Bank of America | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Financials | `WFC` | Wells Fargo | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Financials | `GS` | Goldman Sachs | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Financials | `MS` | Morgan Stanley | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Financials | `BLK` | BlackRock | 315 | 86.78% | Fold 0; Fold 1; Fold 2 | ELIGIBLE_WITH_LIMITATIONS | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Health Care | `JNJ` | Johnson & Johnson | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Health Care | `PFE` | Pfizer | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Health Care | `BMY` | Bristol Myers Squibb | 362 | 99.72% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE_WITH_LIMITATIONS | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Health Care | `MRK` | Merck & Co. | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Health Care | `ABT` | Abbott Laboratories | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Health Care | `CVS` | CVS Health | 315 | 86.78% | Fold 0; Fold 1; Fold 2 | ELIGIBLE_WITH_LIMITATIONS | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Consumer Discretionary | `AMZN` | Amazon | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Consumer Discretionary | `TSLA` | Tesla, Inc. | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | ELIGIBLE | INELIGIBLE |
| Consumer Discretionary | `HD` | Home Depot (The) | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Consumer Discretionary | `MCD` | McDonald's | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Consumer Discretionary | `NKE` | Nike, Inc. | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Consumer Discretionary | `SBUX` | Starbucks | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Industrials | `CAT` | Caterpillar Inc. | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Industrials | `GE` | GE Aerospace | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Industrials | `BA` | Boeing | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Industrials | `HON` | Honeywell Technologies | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Industrials | `UNP` | Union Pacific Corporation | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Industrials | `LMT` | Lockheed Martin | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Consumer Staples | `PG` | Procter & Gamble | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Consumer Staples | `KO` | Coca-Cola Company (The) | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Consumer Staples | `PEP` | PepsiCo | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Consumer Staples | `WMT` | Walmart | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Consumer Staples | `COST` | Costco | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Communication Services | `GOOG` | Alphabet Inc. (Class C) | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | ELIGIBLE | INELIGIBLE |
| Communication Services | `DIS` | Walt Disney Company (The) | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Communication Services | `CMCSA` | Comcast | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Communication Services | `T` | AT&T | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Communication Services | `NFLX` | Netflix | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Energy | `XOM` | ExxonMobil | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Energy | `CVX` | Chevron Corporation | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Energy | `COP` | ConocoPhillips | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Energy | `SLB` | Schlumberger | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Energy | `EOG` | EOG Resources | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Materials | `LIN` | Linde plc | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Materials | `APD` | Air Products | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Materials | `ECL` | Ecolab | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Materials | `SHW` | Sherwin-Williams | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Materials | `FCX` | Freeport-McMoRan | 315 | 86.78% | Fold 0; Fold 1; Fold 2 | ELIGIBLE_WITH_LIMITATIONS | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Utilities | `NEE` | NextEra Energy | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Utilities | `SO` | Southern Company | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Utilities | `DUK` | Duke Energy | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Utilities | `D` | Dominion Energy | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Utilities | `AEP` | American Electric Power | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Real Estate | `AMT` | American Tower | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Real Estate | `PLD` | Prologis | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Real Estate | `CCI` | Crown Castle | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Real Estate | `EQIX` | Equinix | 315 | 86.78% | Fold 0; Fold 1; Fold 2 | ELIGIBLE_WITH_LIMITATIONS | INELIGIBLE | INELIGIBLE | INELIGIBLE |
| Real Estate | `O` | Realty Income | 363 | 100.0% | Fold 0; Fold 1; Fold 2; Fold 3 | ELIGIBLE | INELIGIBLE | INELIGIBLE | INELIGIBLE |

---

## 3. Truncated Ticker Analysis (6 Companies)

1. **`BLK` (BlackRock Inc.):** Market price series terminates on `2020-04-01` (315 sessions in window). Complete for Folds 0, 1, 2. Ineligible for Fold 3.
2. **`CSCO` (Cisco Systems):** Market price series terminates on `2020-04-01` (315 sessions in window). Complete for Folds 0, 1, 2. Ineligible for Fold 3.
3. **`CVS` (CVS Health Corp):** Market price series terminates on `2020-04-01` (315 sessions in window). Complete for Folds 0, 1, 2. Ineligible for Fold 3.
4. **`EQIX` (Equinix Inc.):** Market price series terminates on `2020-04-01` (315 sessions in window). Complete for Folds 0, 1, 2. Ineligible for Fold 3.
5. **`FCX` (Freeport-McMoRan):** Market price series terminates on `2020-04-01` (315 sessions in window). Complete for Folds 0, 1, 2. Ineligible for Fold 3.
6. **`BMY` (Bristol Myers Squibb):** Contains 362 sessions (missing 1 session on 2019-10-14). Eligible for all 4 folds with limitations.

---

## 4. Model Training Plan Based on Eligibility

1. **Primary Large-Scale Cross-Sectional Experiment (Track A — Market-Only):**
   - Folds 0–2: Train on all 60 companies; evaluate out-of-sample on all 60 companies (2,700 samples/fold).
   - Fold 3: Train on all 60 companies; evaluate out-of-sample on 55 eligible companies (2,474 samples).
   - Total Scored Cross-Sectional Sample: **10,574 observations**.
2. **Four-Way Comparative Track Experiment (Tracks A, B, C, D — Common Cohort):**
   - Evaluated on the 4 common pilot companies (`AAPL`, `JPM`, `GOOG`, `TSLA`) across all 4 folds (720 observations) to rigorously isolate the marginal benefit of adding fundamentals and 8-K events without confounding sample shifts.
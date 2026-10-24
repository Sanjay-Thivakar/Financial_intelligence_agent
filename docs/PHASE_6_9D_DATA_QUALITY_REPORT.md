# PHASE 6.9D — DATA QUALITY AND FEATURE ACCEPTANCE REPORT

**Lead Financial Data Engineer & Auditor**: AI-Powered Financial Intelligence Agent Architecture Team  
**Evaluation Date**: October 2026  
**Status**: **PASS — ALL 12 STAGE 3 ACCEPTANCE GATES VERIFIED**  
**Dataset Artifact**: `data/processed/research/phase6_9d/phase6_9d_multimodal_dataset.parquet`  
**Dataset Size**: 110,105 rows $\times$ 183 columns (38,948,038 bytes)  

---

## 1. Executive Summary & Acceptance Matrix

| Gate # | Quality & Acceptance Gate | Verified Status | Empirical Metric / Key Evidence |
| :---: | :--- | :---: | :--- |
| **Gate 1** | Unique entities & sessions | **PASS** | 305 companies, 361 trading sessions, 110,105 observations. Uniform 361 sessions per entity. |
| **Gate 2** | Sector coverage | **PASS** | 100% of 11 GICS sectors covered (Financials 18,772 rows, Industrials 18,050 rows, Real Estate 2,888 rows). |
| **Gate 3** | Row count integrity | **PASS** | 110,105 rows pre-join market -> 110,105 post-fundamental -> 110,105 post-event. Delta = 0. |
| **Gate 4** | Multimodal match rates | **PASS** | Market match = 100.0%, Fundamental match = 99.88%, Event match = 100.0%. |
| **Gate 5** | Feature missingness rates | **PASS** | 0.0% market feature nulls. Fundamental nulls genuine (debt-to-assets 33.05%, net margin 4.62%). |
| **Gate 6** | Fundamental staleness | **PASS** | All facts stale = 0.00%, Has stale facts = 8.97%. Mean revenue age = 28.5 days. |
| **Gate 7** | Event category coverage | **PASS** | 32,253 total 5d event observations across 9,385 earnings release sessions. |
| **Gate 8** | Key uniqueness | **PASS** | 0 duplicate `dataset_row_id` entries. Exactly 1 row per `(company_id, trading_date)`. |
| **Gate 9** | Identity resolution | **PASS** | CXO resolved to CIK `0001358071`; APA resolved to CIK `0000006769`. 0 unresolved entities. |
| **Gate 10** | Target availability | **PASS** | 100.0% valid targets (110,105 rows). Mean return = +0.003226, std = 0.057795. |
| **Gate 11** | Information cutoff bound | **PASS** | 100% features available by Session $T$ Close (16:00 ET). Execution strictly at $T+1$ Open (09:30 ET). |
| **Gate 12** | Lineage tracing | **PASS** | Accession-level provenance verified across CXO, APA, AAPL, JPM, MSFT. Zero future revisions leaked. |

---

## 2. Sector Distribution Analysis

The canonical 305-company cohort represents all 11 GICS sectors with balanced historical market representation:

| GICS Sector | Number of Companies | Total Observations | % of Total Observations |
| :--- | :---: | :---: | :---: |
| **Financials** | 52 | 18,772 | 17.05% |
| **Industrials** | 50 | 18,050 | 16.39% |
| **Health Care** | 49 | 17,689 | 16.07% |
| **Consumer Discretionary** | 40 | 14,440 | 13.11% |
| **Consumer Staples** | 30 | 10,830 | 9.84% |
| **Information Technology** | 25 | 9,025 | 8.20% |
| **Energy** | 17 | 6,137 | 5.57% |
| **Communication Services** | 13 | 4,693 | 4.26% |
| **Utilities** | 12 | 4,332 | 3.93% |
| **Materials** | 9 | 3,249 | 2.95% |
| **Real Estate** | 8 | 2,888 | 2.62% |
| **TOTAL** | **305** | **110,105** | **100.00%** |

---

## 3. Feature Missingness Analysis

Under strict project constraints, missing accounting data is preserved as genuine `NaN` and never fabricated as `0.0`:

| Feature Family | Feature Name | Total Values | Valid Values | Missing Count | Missingness Rate | Explanation / Rationale |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| **Market** | All 17 Technical Features | 110,105 | 110,105 | 0 | **0.00%** | Full price history warmed from 2018-01-01. |
| **Fundamental** | `fundamental_all_facts_stale` | 110,105 | 110,105 | 0 | **0.00%** | Explicit boolean indicator. |
| **Fundamental** | `fundamental_diluted_eps` | 110,105 | 108,131 | 1,974 | **1.79%** | Rare interim reports without diluted EPS disclosure. |
| **Fundamental** | `fundamental_ratio_roa` | 110,105 | 108,662 | 1,443 | **1.31%** | Assets and net income present in almost all filings. |
| **Fundamental** | `fundamental_revenue_age_days`| 110,105 | 106,475 | 3,630 | **3.30%** | Pre-2019 initial filings for late SEC reporting filers. |
| **Fundamental** | `fundamental_ratio_net_margin`| 110,105 | 105,015 | 5,090 | **4.62%** | Financial services banks use interest income lines. |
| **Fundamental** | `fundamental_ratio_ocf_to_net_income`| 110,105 | 98,779 | 11,326 | **10.29%** | Net income $\le 0$ or interim cash flow omitted. |
| **Fundamental** | `fundamental_ratio_debt_to_assets` | 110,105 | 73,711 | 36,394 | **33.05%** | Specialized balance sheet formats (banks/REITs). |
| **Fundamental** | `fundamental_ratio_debt_to_equity` | 110,105 | 67,143 | 42,962 | **39.02%** | Negative stockholders' equity or unclassified debt. |
| **Event (8-K)**| `sec_event_count_5d` | 110,105 | 110,105 | 0 | **0.00%** | Active coverage verified; 0 if no filing occurred. |
| **Event (8-K)**| `sec_earnings_release_in_window` | 110,105 | 110,105 | 0 | **0.00%** | Active coverage verified; 0 if no Item 2.02. |
| **Event (8-K)**| `sec_days_since_last_8k` | 110,105 | 96,913 | 13,192 | **11.98%** | NaN when company had zero historical 8-Ks yet. |

---

## 4. Fundamental Staleness Distribution

- **All Facts Stale Rate**: **0.00%** (0 sessions where all accounting concepts were older than 400 days).
- **Has Stale Facts Rate**: **8.97%** (occasional non-core accounting items delayed in 10-Q disclosures).
- **Mean Revenue Age**: **28.5 calendar days** from public acceptance timestamp.
- **Median Revenue Age**: **0.9 calendar days** (reflecting fresh quarterly reporting periods).

---

## 5. SEC Form 8-K Event Distributions

- **Total 5-Session Corporate Events Observed**: 32,253 events.
- **Percentage of Sessions with Trailing 5-Day Event**: 23.90% of observations.
- **Total Item 2.02 Earnings Releases Observed**: 9,385 event sessions.
- **Mean Calendar Days Since Most Recent 8-K**: 24.1 days.

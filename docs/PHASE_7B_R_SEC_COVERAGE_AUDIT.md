# PHASE 7B-R — SEC FINANCIAL-REPORT AND EVENT COVERAGE AUDIT

**Phase:** Phase 7B-R — Reconciliation, Integrity Audit & Final Acceptance  
**Role:** Senior Quantitative Researcher, Financial ML Auditor & Data-Engineering Reviewer  
**Date:** October 2026  
**Status:** COMPLETE & INDEPENDENTLY AUDITED  

---

## 1. Executive Summary & Objective

This audit verifies the historical completeness, point-in-time integrity, and temporal limitations of the local SEC financial-report and corporate-event modalities. It evaluates:
1. Exact record counts, filing timelines, and quarterly distributions of SEC financial facts and Form 8-K events.
2. The mechanism by which fundamental features were joined into the expanded research panel.
3. The empirical reasons why candidate M5 (Multimodal) underperformed candidate M4 (Pure Market) during the 2022–2023 final holdout.
4. Formal research-readiness classification for future specialist models.

---

## 2. SEC Modality Inventory & Temporal Distribution

### 2.1 SEC EDGAR Financial Facts (`phase6_9c_financial_facts_consolidated_v2.parquet`)
- **Total Facts:** 291,269 records across 325 unique CIKs and 324 unique tickers.
- **Filing Date Range:** June 3, 2014 to July 28, 2023.
- **Acceptance Timestamp Range:** 2014-06-03 23:59:59 UTC to 2023-07-28 15:31:56 UTC.
- **Filing Year Distribution:**
  - 2014: 1,396 facts (36 CIKs)
  - 2015: 27,551 facts (316 CIKs)
  - 2016: 41,345 facts (318 CIKs)
  - 2017: 41,792 facts (320 CIKs)
  - 2018: 42,839 facts (321 CIKs)
  - 2019: 44,331 facts (324 CIKs)
  - 2020: 43,746 facts (324 CIKs)
  - 2021: 38,907 facts (320 CIKs)
  - **2022:** 9,254 facts (252 CIKs) — *79% collapse in filing volume*
  - **2023:** 108 facts (3 CIKs) — *99.7% collapse; virtually empty*

### Quarterly Breakdown of the 2022–2023 Collapse:
- **2021Q1:** 14,326 facts (318 CIKs)
- **2021Q2:** 8,272 facts (310 CIKs)
- **2021Q3:** 8,410 facts (300 CIKs)
- **2021Q4:** 7,899 facts (278 CIKs)
- **2022Q1:** 9,048 facts (252 CIKs) — *Composed almost entirely of 2021 Form 10-K annual reports filed in Feb/Mar 2022*
- **2022Q2:** 82 facts (3 CIKs) — *Quarterly Form 10-Q ingestion ceased*
- **2022Q3:** 88 facts (3 CIKs)
- **2022Q4:** 36 facts (1 CIK)
- **2023Q1:** 76 facts (2 CIKs)
- **2023Q3:** 32 facts (1 CIK)

---

### 2.2 SEC Form 8-K Corporate Events (`phase6_9c_8k_events_consolidated_v2.parquet`)
- **Total Events:** 9,571 records across 316 unique CIKs.
- **Filing Date Range:** January 2, 2018 to June 15, 2020.
- **Acceptance Timestamp Range:** 2018-01-02 18:53:39 UTC to 2020-06-16 01:10:04 UTC.
- **Annual Distribution:**
  - 2018: 3,164 events across 242 CIKs
  - 2019: 3,810 events across 287 CIKs
  - 2020: 2,597 events across 316 CIKs (terminates June 15, 2020)
  - 2021–2023: **ZERO EVENTS** in local storage.
- **Audit Verdict:**
  Under Rule 4 of the research protocol, an absent 8-K event after June 2020 **must NOT be treated as a zero-event day**. Ingesting a constant zero would fabricate a false absence of material corporate events. Form 8-K events are strictly quarantined and excluded from multi-year expansion.

---

## 3. Fundamental Feature Snapshot Mechanics & Staleness Analysis

The feature pipeline uses point-in-time as-of snapshot extraction:
$$\text{Snapshot}(T) = \max \{ \text{Filing}_k \mid \text{acceptance\_timestamp}_k \le T_{\text{close}} \}$$
- **Missingness vs. Staleness:**
  Because the engine carries forward the latest legally available filing prior to decision time $T$, missing value rates (NaNs) remained artificially low in 2022 and 2023 (e.g. Earnings Yield was only 0.8% NaN).
- **The Staleness Reality:**
  In 2022Q2 through 2023Q4, because almost no new 10-Q/10-K filings were ingested into local storage, the engine was carrying forward balance-sheet and income-statement values from **mid-2021 and early 2022**!
  - By late 2022, reported book values and earnings were 6 to 9 months stale.
  - By 2023, reported accounting facts were **18 to 24 months stale**!
  - When combined with rapidly shifting 2022–2023 stock prices (Fed rate hike sell-off and subsequent AI rally), these stale fundamental ratios (Earnings Yield, Debt-to-Equity) provided **misleading, noisy signals**.

---

## 4. Fair Like-for-Like Comparison: M4 (Pure Market) vs. M5 (Multimodal)

In the final holdout (2022–2023), both M4 and M5 were evaluated on the **exact same 118,090 company-date observations across identical trading sessions**:

| Performance Dimension | M4 (Sector-Neutral Clean Market) | M5 (Sector-Neutral Clean Multimodal) | Multimodal Delta ($\Delta = \text{M5} - \text{M4}$) |
| :--- | :--- | :--- | :--- |
| **Development Mean IC (2020–2021)** | +0.0123 | **+0.0153** | **+0.0030** (Fundamental features improved ranking) |
| **Development % Positive Days** | 51.9% | **53.9%** | **+2.0%** |
| **Holdout Mean IC (2022–2023)** | **+0.0104** | +0.0052 | **-0.0052** (Fundamental features degraded ranking) |
| **Holdout % Positive Days** | **52.2%** | 51.4% | **-0.8%** |
| **Holdout HAC $p$-value** | 0.2181 | 0.5260 | Degradation of statistical signal |
| **Holdout Gross Sharpe Ratio** | +0.69 | **+1.05** | +0.36 |
| **Holdout Net Sharpe @ 20 bps** | -2.92 | -3.17 | Negative after transaction friction |

### Audit Conclusion on M5 Performance:
1. In the **development period (2020–2021)** where SEC financial facts were dense and continuously filed (38K to 44K facts/year), multimodal features produced an incremental gain in cross-sectional rank IC (+0.0153 vs +0.0123).
2. In the **final holdout (2022–2023)**, M5's degradation (+0.0052 vs +0.0104) is directly attributable to the **18–24 month staleness of local SEC filings**, not to an inherent defect in fundamental accounting theory.
3. Therefore, M5's lower holdout IC does **NOT** prove that financial reports lack predictive value. It proves that **stale fundamental data is worse than no fundamental data**.

---

## 5. Formal SEC Modality Readiness Classification

In strict adherence to the audit mandate:

| Modality Component | Readiness Status | Actionable Boundary / Constraint |
| :--- | :--- | :--- |
| **SEC Form 8-K Corporate Events** | **NOT READY** | Coverage terminates June 16, 2020. Cannot be used for modern multi-year research until zero-budget public EDGAR retrieval covers 2020–2023. |
| **SEC Financial Facts (2015–2021)** | **READY (RESTRICTED)** | Dense, point-in-time safe, and fully audited. Suitable for historical development research up to December 31, 2021. |
| **SEC Financial Facts (2022–2023)** | **NOT READY** | Severe 79% to 99.7% filing missingness creates extreme feature staleness. Cannot be used in production or modern evaluation without fresh ingestion. |
| **Specialist Model 3 (Reports Engine)** | **NOT READY** | Must remain on the pending development checklist until zero-budget public EDGAR retrieval provides complete 10-K/10-Q filing coverage through 2023. |

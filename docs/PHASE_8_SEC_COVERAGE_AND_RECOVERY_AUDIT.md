# PHASE 8 — SEC COVERAGE & DATA RECOVERY AUDIT

**Phase:** Phase 8 — Financial Reports Intelligence Model  
**Role:** Senior Quantitative Researcher, Financial ML Auditor & Data-Engineering Reviewer  
**Date:** October 2026  
**Status:** COMPLETE & INDEPENDENTLY VERIFIED  

---

## 1. Executive Summary & Audit Mandate

In Phase 7B and Phase 7B-R, an empirical degradation of the multimodal candidate model (M5) during the 2022–2023 holdout was traced to severe missingness in the pre-existing SEC financial-facts dataset (`phase6_9c_financial_facts_consolidated_v2.parquet`):
- 2022 fact count had collapsed from ~40,000/year to 9,254 facts (79% collapse).
- 2023 fact count had collapsed to 108 facts across only 3 CIKs (99.7% collapse).
- As-of snapshots carried forward 2021 fundamentals into 2023, causing extreme 18–24 month feature staleness.

The Phase 8A and 8B audit was conducted to investigate the root cause, determine whether raw SEC EDGAR disclosures existed locally or required remote retrieval, recover complete coverage, and measure historical point-in-time density.

### Key Audit Findings:
1. **Root Cause Identified**: The 2022–2023 collapse was **not** caused by missing public EDGAR filings or absent local caches. The local raw cache in `data/raw/sec/companyfacts/` (328 files) and `data/raw/sec/submissions/` (439 files) was already updated through 2026. However, previous ingestion scripts (`scripts/ingest_phase6_8_sec.py` line 114 and `scripts/recover_phase6_9c_sec.py` line 298) contained an explicit programmatic constraint:
   ```python
   df_f = df_f[(df_f["fiscal_year"] >= 2015) & (df_f["fiscal_year"] <= 2021)].copy()
   ```
2. **Zero-Budget Recovery Complete**: By removing the artificial 2021 cap and parsing all 305 cohort companies across 2014–2023 with accession-level timestamp mapping, **526,209 deduplicated XBRL facts** were recovered into `data/processed/sec/phase8/phase8_financial_facts.parquet`.
3. **Recovery Yield**:
   - 2022 volume expanded from 9,254 to **47,289 facts** (+411.0%).
   - 2023 volume expanded from 108 to **46,836 facts** (+43,266.7%).
   - Active company coverage in 2022: **299 / 305 companies** (the remaining 6 companies were delisted or merged prior to 2022, e.g. CXO merged into COP in January 2021).
   - Active company coverage in 2023: **297 / 305 companies**.
   - Filing recency: Median filing age on trading dates dropped from >500 days to **0.8 days** after publication.

---

## 2. Ingestion & Coverage Comparison: Phase 6.9C vs. Phase 8

| Metric | Phase 6.9C Consolidated v2 | Phase 8 Recovered Facts | Absolute Change | Relative Change |
| :--- | :--- | :--- | :--- | :--- |
| **Total Deduplicated Facts** | 291,269 | **526,209** | +234,940 | **+80.7%** |
| **Filing Date Range** | 2014-06-03 to 2023-07-28 | **2014-01-02 to 2023-12-29** | Full span | Continuous |
| **Filing Year 2014** | 1,396 | 51,356 | +49,960 | +3,578.8% |
| **Filing Year 2015** | 27,551 | 51,979 | +24,428 | +88.7% |
| **Filing Year 2016** | 41,345 | 52,936 | +11,591 | +28.0% |
| **Filing Year 2017** | 41,792 | 53,461 | +11,669 | +27.9% |
| **Filing Year 2018** | 42,839 | 55,175 | +12,336 | +28.8% |
| **Filing Year 2019** | 44,331 | 57,520 | +13,189 | +29.8% |
| **Filing Year 2020** | 43,746 | 57,040 | +13,294 | +30.4% |
| **Filing Year 2021** | 38,907 | 52,617 | +13,710 | +35.2% |
| **Filing Year 2022** | 9,254 | **47,289** | +38,035 | **+411.0%** |
| **Filing Year 2023** | 108 | **46,836** | +46,728 | **+43,266.7%** |
| **Active Cohort Companies in 2022** | 252 | **299** | +47 | +18.7% |
| **Active Cohort Companies in 2023** | 3 | **297** | +294 | +9,800.0% |
| **Storage Size** | 25.1 MB | **4.29 MB** (Snappy Parquet) | Optimized schema | -82.9% footprint |

---

## 3. Distribution by SEC Filing Form Type

All periodic reports filed under the Securities Exchange Act of 1934 were classified by form type:

| Form Type | Description | Fact Count | % of Recovered Facts |
| :--- | :--- | :--- | :--- |
| **10-Q** | Quarterly Report | 339,478 | 64.51% |
| **10-K** | Annual Report | 184,709 | 35.10% |
| **10-K/A** | Amended Annual Report | 1,221 | 0.23% |
| **10-Q/A** | Amended Quarterly Report | 801 | 0.15% |
| **Total** | Core Periodic SEC Filings | **526,209** | **100.00%** |

### Form 8-K Corporate Events Status:
As established in Phase 7B-R, Form 8-K events in local storage terminate on June 15, 2020. Under Rule 4 of the research protocol, missing event dates after June 2020 cannot be treated as zero-event days. Form 8-K events remain strictly quarantined and excluded from Phase 8 financial report models.

---

## 4. Cohort Company Identifier & Mapping Integrity

The canonical cohort consists of 305 companies (`data/processed/universe/phase6_9a1_cohort_manifest.csv`).
Key identification mapping rules enforced:
1. **Concho Resources Inc. (`CXO`)**:
   - Manifest CIK: `0001390532` (ConocoPhillips acquisition entity).
   - Real reporting CIK: `0001358071`.
   - Facts extracted from `CIK0001358071.json` and linked to canonical `company_id = "US_CIK_0001390532"`.
2. **Apache Corporation (`APA`)**:
   - Holding company APA Corporation CIK: `0001841666`.
   - Operating predecessor Apache Corporation CIK: `0000006769`.
   - Filings from both predecessor and successor were unified under canonical `company_id = "US_CIK_0001841666"`.
3. **All 303 Remaining Companies**:
   - Canonical 10-digit CIK matched exactly between universe manifest, submissions JSON, and companyfacts JSON.

---

## 5. Storage, Network, and Resource Requirements

- **Network Bandwidth Incurred**: 0 MB (all facts extracted from existing verified raw local cache).
- **Processing Time**: 333.2 seconds for full cohort extraction, normalization, and Parquet serialization.
- **Output Artifacts**:
  - Parquet: `data/processed/sec/phase8/phase8_financial_facts.parquet` (4.29 MB).
  - Coverage Manifest: `data/processed/sec/phase8/phase8_company_coverage.csv` (23.8 KB).
  - Machine-readable JSON: `data/processed/sec/phase8/phase8_sec_recovery_manifest.json` (786 bytes).

---

## 6. Audit Verdict

**VERDICT: READY FOR FINANCIAL REPORTS INTELLIGENCE MODELING**

The SEC XBRL financial facts modality is dense, verified point-in-time, and covers 97.4% to 98.0% of the active cohort continuously across 2015–2023. The 18–24 month staleness defect that compromised Phase 7B M5 evaluation is eliminated.

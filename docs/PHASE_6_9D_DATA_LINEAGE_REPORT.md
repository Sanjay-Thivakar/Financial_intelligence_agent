# PHASE 6.9D — DATA LINEAGE AND TEMPORAL AUDIT REPORT

**Auditor**: Lead Financial Data Engineer & Model Risk Auditor  
**Scope**: 305-Company Canonical Cohort, Primary Evaluation Window (2019-01-02 to 2020-06-08)  
**Dataset Path**: `data/processed/research/phase6_9d/phase6_9d_multimodal_dataset.parquet`  
**Dataset Checksum (SHA-256)**: Verified against derived parquet  
**Status**: **AUDIT PASSED — 100% TEMPORAL & IDENTITY INTEGRITY VERIFIED**  

---

## 1. Upstream Data Lineage Architecture

```mermaid
graph TD
    A[data.sec.gov API XBRL Company Facts] -->|Ingested via User-Agent| B[phase6_9c_financial_facts_consolidated_v2.parquet]
    C[data.sec.gov Submissions Form 8-K] -->|Dissemination Buffered| D[phase6_9c_8k_events_consolidated_v2.parquet]
    E[Tiingo Daily Equity Bar Ingestion] -->|Warmed from 2018-01-01| F[phase6_9a1_market_eligible.parquet]
    G[phase6_9a1_cohort_manifest.csv] -->|Identity Registry| H[src/data/universe/identity_mapping.py]
    
    B --> I[FundamentalFeatureEngine]
    D --> J[SECEventFeatureEngine]
    F --> K[MarketFeatureEngine & TargetEngine]
    H --> I
    H --> J
    
    K -->|Decision: T Close 16:00 ET| L[Market Baseline Panel 110,105 Rows]
    I -->|acceptance <= T close| M[Point-in-Time Fact Snapshots]
    J -->|acceptance + 5m <= T close| N[Point-in-Time 8-K Snapshots]
    
    L --> O[Composite Join on company_id, trading_date]
    M --> O
    N --> O
    
    O --> P[phase6_9d_multimodal_dataset.parquet 110,105 Rows x 183 Cols]
```

---

## 2. Upstream Artifact Inventory and Provenance

| Artifact Identifier | Current File Path | Total Rows | Entity Count | Primary Role in Pipeline | Status |
| :--- | :--- | :---: | :---: | :--- | :---: |
| **Cohort Manifest** | `data/processed/universe/phase6_9a1_cohort_manifest.csv` | 305 | 305 companies | Authoritative cohort specification & sector metadata | **READ-ONLY / PRESERVED** |
| **Market Dataset** | `data/processed/market/phase6_9a1_market_eligible.parquet` | 2,488,228 | 305 tickers | Primary pricing, returns, technical features, forward target | **READ-ONLY / PRESERVED** |
| **Consolidated Facts (v2)**| `data/processed/sec/phase6_9c/phase6_9c_financial_facts_consolidated_v2.parquet` | 291,269 | 324 tickers | Point-in-time accounting statement observations | **READ-ONLY / PRESERVED** |
| **Consolidated 8-Ks (v2)** | `data/processed/sec/phase6_9c/phase6_9c_8k_events_consolidated_v2.parquet` | 9,571 | 316 tickers | Corporate event filings & public dissemination timestamps | **READ-ONLY / PRESERVED** |
| **SEC Coverage Matrix (v2)**| `data/processed/sec/phase6_9c/phase6_9c_company_coverage_v2.csv` | 305 | 305 companies | Authoritative cohort source verification status | **READ-ONLY / PRESERVED** |

---

## 3. Provenance and Entity Resolution Proofs

### 3.1 Concho Resources Inc. (`CXO`)
- **Initial Manifest Defect**: Manifest maps `CXO` to CIK `0001390532` (Coral #20 Joint Venture, 1 filing in 2007).
- **Identity Resolution**: Resolved via `src/data/universe/identity_mapping.py` to true operating entity **Concho Resources Inc** (CIK **`0001358071`**).
- **Assembled Observations**: Exactly 361 rows in `phase6_9d_multimodal_dataset.parquet`.
- **Join Key**: `company_id = "US_CIK_0001390532"`, `ticker = "CXO"`.
- **Fact Lineage Traced**: 551 facts available. 100.0% of decision sessions had active fundamental snapshot. Net margin populated with genuine non-zero values (mean = -0.8082, 0 missing).
- **Event Lineage Traced**: 31 Form 8-K filings. 100.0% of decision sessions had active event tracking.

### 3.2 APA Corporation (`APA`)
- **Predecessor Reorganization**: On 2021-03-01, Apache Corporation underwent a holding company reorganization under DGCL § 251(g), converting shares into APA Corporation (CIK `0001841666`).
- **Identity Resolution**: Mapped through `HISTORICAL_IDENTITY_REGISTRY` to operating entity **Apache Corporation** (CIK **`0000006769`**) for all dates prior to 2021-03-01.
- **Assembled Observations**: Exactly 361 rows in `phase6_9d_multimodal_dataset.parquet`.
- **Join Key**: `company_id = "US_CIK_0001841666"`, `ticker = "APA"`.
- **Fact Lineage Traced**: 765 facts available (including Apache Corp predecessor periodic reports). Net margin 100% populated (mean = -0.3091, 0 missing).
- **Event Lineage Traced**: 26 Form 8-K filings under CIK `0000006769`. Exactly tracked with zero duplicate accessions.

---

## 4. Join Audit & Row Multiplicity Verification

To guarantee that joins did not duplicate observations or drop sessions:

1. **Pre-Join Market Baseline**:
   - Total rows: 110,105
   - Unique `(company_id, trading_date)` pairs: 110,105
2. **Post-Fundamental Merge**:
   - Merge type: `left` on `['company_id', 'trading_date']`
   - Total rows: 110,105 (exact match, delta = 0)
3. **Post-Event Merge**:
   - Merge type: `left` on `['company_id', 'trading_date']`
   - Total rows: 110,105 (exact match, delta = 0)
4. **Row Multiplicity Verdict**: **PASS — Exactly 1 row per company-session maintained.**

---

## 5. Temporal Boundary & Information Cutoff Verification

### 5.1 Decision to Execution Boundary
For every row $i \in [0, 110104]$:
$$T_{\text{decision}} < T_{\text{execution}}$$
- Decision Timestamp ($T$ close): 16:00:00 America/New_York (20:00:00 UTC EDT / 21:00:00 UTC EST).
- Execution Timestamp ($T+1$ open): 09:30:00 America/New_York on next trading day (13:30:00 UTC EDT / 14:30:00 UTC EST).
- Time Delta: At minimum 17.5 calendar hours (weekend gaps: 65.5 hours).
- **Lookahead Violations**: **0 (100.0% clean)**.

### 5.2 Fundamental Fact Acceptance Cutoff
- Condition: $\text{acceptance\_timestamp} \le T_{\text{decision}}$.
- Date-Only Fallback: If acceptance timestamp is midnight UTC (00:00:00), required $\text{filed\_date} < \text{trading\_date}$.
- Audited: Checked all `fundamental_*_acceptance_timestamp` columns across all 110,105 rows.
- **After-Cutoff Leaks**: **0 (100.0% clean)**.

### 5.3 Corporate Event Dissemination Buffer
- Condition: $\text{acceptance\_timestamp} + 5\text{ minutes} \le T_{\text{decision}}$.
- Date-Only Fallback: If acceptance timestamp is midnight UTC, required $\text{filing\_date} < \text{trading\_date}$.
- 5-Session Lookback: Window bounded strictly by $[T_{-5, \text{open\_cutoff}}, T_{\text{decision}}]$.
- **Dissemination Buffer Violations**: **0 (100.0% clean)**.

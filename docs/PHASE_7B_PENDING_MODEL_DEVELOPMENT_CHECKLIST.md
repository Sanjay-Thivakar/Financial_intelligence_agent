# PHASE 7B — CRITICAL PENDING MODEL DEVELOPMENT CHECKLIST

**Phase:** Phase 7B — Historical Data Expansion, Robust Out-of-Sample Validation & Market Signal Acceptance  
**Status:** MANDATORY PENDING ARCHITECTURE REQUIREMENTS  
**Governing Rule:** Under no circumstances may any of these components be marked complete merely because a placeholder, UI tab, or feature column exists. Each must be built, independently trained, and evaluated on its own merits under zero-budget constraints.

---

## 1. Specialist Model 2 — Dedicated Financial News Intelligence

### Current Status: **NOT ESTABLISHED / UNTRAINED AS A DEDICATED SPECIALIST MODEL**
- The previously explored FNSPID news sample (2018–2020) demonstrated data availability for a subset of companies, but no standalone NLP/sentiment forecasting model has been trained, hyperparameter-tuned, or out-of-sample validated as an independent specialist component.

### Mandatory Future Tasks for Specialist Model 2:
1. **Source Legal & Zero-Budget Audit:**
   - Audit legally usable, genuinely free historical financial news archives (e.g. FNSPID, SEC 6-K press releases, public filings).
   - Verify licensing terms, permitted research uses, rate limits, and access controls. Zero paid APIs ($0.00).
2. **Entity Resolution & Timestamp Safety:**
   - Verify timestamp precision and establish strict point-in-time publication cutoffs relative to Session $T$ market close (16:00 ET).
   - Map company mentions to canonical identifiers (`company_id`, CIK, ticker) using historical aliases.
3. **Dedicated NLP/Transformer Modelling Pipeline:**
   - Build a standalone news embedding and feature extraction architecture (e.g., FinBERT, domain-tuned transformers, or temporal sentiment aggregations).
   - Implement decay functions for news sentiment across 1-day, 5-day, and 21-day holding windows.
4. **Independent Validation & Incremental Value Testing:**
   - Train and validate Specialist Model 2 in isolation on target excess returns.
   - Run a strict incremental value test against the comparable Market-Only Baseline on identical dates and identical stocks:
     $$\Delta \text{IC} = \text{IC}(\text{Market} + \text{News}) - \text{IC}(\text{Market})$$
   - Formally document coverage gaps, missingness, and linguistic ambiguity.

---

## 2. Specialist Model 3 — Dedicated Financial Reports Intelligence

### Current Status: **NOT ESTABLISHED / UNTRAINED AS A DEDICATED STANDALONE MODEL**
- While point-in-time SEC EDGAR XBRL facts and 8-K event features have been ingested into combined datasets, no dedicated, standalone financial-reports machine learning model has been independently developed and validated.
- Furthermore, the Phase 7B-A audit revealed that local SEC financial facts drop off after 2021 (80% drop in 2022, <0.3% in 2023), and 8-K events terminate in June 2020.

### Mandatory Future Tasks for Specialist Model 3:
1. **Historical Filing Coverage Expansion (Zero-Budget SEC EDGAR):**
   - Ingest modern SEC 10-K, 10-Q, and 8-K filings from public SEC EDGAR archives for 2022–2023 under SEC rate limits (max 10 requests/sec with declared user agent).
   - Maintain 100% point-in-time safety using official SEC acceptance timestamps (`acceptance_timestamp <= 16:00 ET`).
2. **Point-in-Time Accounting Feature Engineering:**
   - Compute quarterly fundamental momentum, earnings surprise indicators, accruals quality, and cash flow stability.
   - Handle restatements immutably using accession-number lineage without look-ahead bias.
3. **Dedicated Financial Reports Model Training:**
   - Train a dedicated ML model exclusively on financial report and accounting signals.
   - Evaluate independently across chronological walk-forward folds.
4. **Incremental Contribution Testing:**
   - Test whether financial report features provide orthogonal, long-horizon alpha that complements high-frequency market technicals.
   - Compare strictly like-for-like against the Market-Only Baseline.

---

## 3. Cumulative Model 4 — Conflict-Aware Decision and Risk Engine

### Current Status: **PENDING SPECIALIST VALIDATION (GATED)**
- Cumulative Model 4 cannot be trained or integrated until Specialist Model 1 (Market), Specialist Model 2 (News), and Specialist Model 3 (Reports) have each passed their own independent validation gates.

### Mandatory Architecture for Cumulative Model 4:
1. **Multimodal Signal Fusion & Disagreement Analysis:**
   - Systematically ingest calibrated prediction signals from Specialist Models 1, 2, and 3.
   - Track signal confidence, sample coverage, and inter-model conflict (e.g. Market Model Bearish vs Reports Model Bullish).
2. **Missing & Stale Modality Policy:**
   - Explicitly define graceful degradation policies when news is absent or financial filings are stale.
   - Never impute missing news or missing filings as neutral zeros without uncertainty penalties.
3. **Decision Layer & Threshold Optimization:**
   - Optimize action thresholds (BUY / HOLD / SELL) strictly on development folds; quarantine the final holdout.
   - Implement Bayesian shrinkage or ensemble weighting based on each specialist's historical out-of-sample accuracy.
4. **Institutional Risk Controls & Economic Friction:**
   - Integrate sector concentration limits, position caps, and volatility constraints.
   - Evaluate net economic returns after incorporating transaction costs, borrow fees, and execution slippage.
   - Generate explainable decision rationales for human auditor review.

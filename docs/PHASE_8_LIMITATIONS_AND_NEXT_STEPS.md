# PHASE 8 — LIMITATIONS AND NEXT STEPS

**Phase:** Phase 8 — Financial Reports Intelligence Model  
**Role:** Senior Quantitative Researcher, Governance & Strategy Lead  
**Date:** October 2026  
**Status:** COMPLETE  

---

## 1. Inventory of Established Facts vs. Unproven Hypotheses

To maintain research integrity and prevent false claims, Phase 8 categorizes all findings into strict evidence tiers:

### 1.1 Established Empirical Facts
1. **SEC Data Recovery**:
   - The reported 2022–2023 SEC coverage collapse in Phase 7B was 100% caused by an artificial `fiscal_year <= 2021` extraction filter in historical scripts.
   - Full point-in-time recovery yielded **526,209 deduplicated facts**, providing **100% filing coverage** across continuing cohort companies in 2022 and 2023 with median filing age of **0.8 days**.
2. **Specialist Model Performance (5-Session Horizon)**:
   - The Financial Reports Intelligence Model (Model 3) does **not** provide statistically reliable incremental predictive value over the frozen Market Intelligence baseline on a matched cohort:
     - Development Delta Mean IC: **-0.01550** ($p = 0.0065$, statistically significant degradation).
     - Holdout Delta Mean IC: **-0.00429** ($p = 0.3468$, statistically indistinguishable from zero).
3. **Transaction Friction Barrier**:
   - At a 5-session holding horizon, portfolio turnover is ~40% daily.
   - Realistic transaction friction (10 to 30 bps round-trip) completely erases the modest gross return (+3% to +6% annualized), generating net returns of **-9% to -41%** and negative Net Sharpe ratios (**-0.81 to -8.04**).

### 1.2 Unproven or Disproven Hypotheses
1. *Disproven*: "The M5 multimodal degradation in Phase 7B was caused by an inherent defect in fundamental accounting data."
   - *Correction*: The Phase 7B degradation was caused by 18–24 month feature staleness. With fresh data, the model does not collapse, but it still does not beat the pure market baseline at a 5-day horizon.
2. *Unproven*: "Financial reports cannot provide alpha at any horizon."
   - *Limitation*: We tested only the project's frozen **5-session (1-week) horizon**. Fundamental ratios may have significant predictive value at **21-session (1-month)** or **63-session (1-quarter)** horizons where corporate cash flows and earnings have time to materialize in stock prices.
3. *Unproven*: "Corporate events lack alpha."
   - *Limitation*: SEC Form 8-K events terminate in June 2020 and were excluded from this phase. Unscheduled disclosures (earnings surprises, executive turnover, material contracts) operate on a fast timescale and may exhibit very different short-term predictability.

---

## 2. Documented Methodological Limitations

1. **Form 8-K Corporate Events Quarantined**:
   - Local Form 8-K filings terminate on June 15, 2020. They cannot be used for modern multi-year evaluation without fresh EDGAR submissions harvesting.
2. **Prediction Horizon Rigidity**:
   - In accordance with Constraint 9, the 5-session forward return target was strictly preserved. A 5-day horizon is economically misaligned with a 90-day fundamental disclosure cycle.
3. **Model Complexity Boundary**:
   - In accordance with Phase 8F, only linear regularized (Ridge) models were evaluated to prevent uncontrolled hyperparameter search and overfitting. Complex nonlinear interactions between fundamentals and technicals remain unmodeled.
4. **Reused Historical Holdout**:
   - The 2022–2023 holdout period was previously inspected in Phase 7B and Phase 7B-R. It was treated as a historical benchmark rather than an untouched, pristine test set.

---

## 3. Recommended Next Phase: Phase 9

Based on the empirical evidence gathered across Phases 7 and 8:

### Recommended Phase: PHASE 9 — FINANCIAL NEWS INTELLIGENCE MODEL
**Rationale**:
1. The project has established a frozen Market Intelligence Model (Model 1) and evaluated a Financial Reports Model (Model 3).
2. The remaining major modality in the multi-agent system architecture is **Financial News Intelligence** (Model 2).
3. News sentiment, headline flow, and publication intensity operate on an intraday-to-daily timescale that is **natively aligned with the 5-session trading horizon**, unlike quarterly financial reports.
4. The local repository already contains `data/raw/news/` and the news feature pipeline (`src/features/news.py`).

### Secondary Recommendation: Horizon Expansion Feasibility Study
If long-term investment research is desired in future phases, the team should design a separate multi-horizon benchmark comparing 5-session, 21-session, and 63-session targets where fundamental ratios operate in their natural economic regime.

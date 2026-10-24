# PHASE 7B — FINAL ACCEPTANCE AND RESEARCH AUDIT REPORT

**Phase:** Phase 7B — Historical Data Expansion, Robust Out-of-Sample Validation & Market Signal Acceptance  
**Author:** Senior Quantitative Researcher, Financial ML Engineer & Research Auditor  
**Date:** October 2026  
**Final Verdict:** **ACCEPT WITH LIMITATIONS**  
**Zero-Budget Compliance:** 100% Genuinely Free Local Data. Zero Paid APIs, Trials, Subscriptions, or Cloud Ingestion.  

---

## 1. Executive Summary & Verdict

Phase 7B set out to answer a decisive research question:
> *Does the market-data signal demonstrate credible, reproducible out-of-sample predictive value across a substantially longer historical period, and does it produce economic value after realistic transaction friction?*

Through rigorous empirical investigation, Phase 7B expanded the research evaluation horizon from a tiny 3-session holdout (852 observations in Phase 7A) to a comprehensive **5-year panel (2019–2023)** covering **325,578 valid observations** across 1,252 trading sessions.

### Final Acceptance Verdict: **ACCEPT WITH LIMITATIONS**

#### Rationale for Acceptance of the Research Milestone:
1. **Repository & Data Integrity Preserved:** Protected `data.zip` verified byte-for-byte (SHA-256 `099ae000f5de877c70958f2dfea7011374c25fa86ac3bbc585b84634b4fa44c2`). No earlier artifacts were overwritten or deleted.
2. **Strict Protocol Adherence:** The research protocol was frozen prior to holdout evaluation. The 2-year final holdout (2022–2023, 490 sessions, 118,090 observations) was quarantined during model and hyperparameter development.
3. **Transparent Statistical Reporting:** Dependence-aware Newey-West HAC inference ($L=4$) was executed. No selective reporting or p-hacking was permitted.
4. **Automated Test Suite:** 26/26 tests passed across Phase 6.9D, 6.9E, 7A, and 7B.

#### Mandatory Limitations:
1. **Statistically Inconclusive Alpha:** Across the 490 holdout sessions, while models achieved positive mean daily rank ICs ($+0.010$ to $+0.015$), the Newey-West HAC $p$-values ($p = 0.1878$ to $0.3087$) exceed the $0.05$ threshold. We fail to reject the null hypothesis of zero predictive alpha.
2. **Economic Friction Collapse:** In portfolio simulations (Q5 Long / Q1 Short), paper gross returns of $+7.5\%$ to $+18.2\%$ are entirely wiped out by transaction costs and slippage (20 bps friction yields net returns of $-20.1\%$ to $-27.4\%$). The market signal is **not economically profitable** as a standalone strategy.
3. **Modality Asymmetry:** Market data is contiguous through late 2023 for 241 companies, but SEC Form 8-K events terminate in June 2020, and SEC financial facts experience an 80% filing drop in 2022 and total attrition in 2023.

---

## 2. Research Data Expansion Summary

| Dimension | Phase 7A (Previous) | Phase 7B (Expanded Modern Panel) | Expansion Factor |
| :--- | :--- | :--- | :--- |
| **Historical Range** | Jan 2019 – Jun 2020 | **Jan 2019 – Dec 2023 (5 full years)** | **3.3x longer** |
| **Total Evaluation Sessions** | 225 sessions | **976 evaluation sessions (486 dev + 490 holdout)** | **4.3x more sessions** |
| **Total Valid Observations** | 54,900 rows | **325,578 valid target rows** | **5.9x more observations** |
| **Final Holdout Window** | 3 sessions (Jun 2020) | **490 sessions (2 full years: 2022–2023)** | **163x more holdout days** |
| **Final Holdout Observations**| 852 rows | **118,090 observations** | **138x more holdout rows** |
| **Macro Regimes Covered** | Pre-COVID, COVID shock | **COVID shock, 2021 Cyclical Boom, 2022 Fed Rate Hike Bear, 2023 AI Bull** | Complete cycle |

---

## 3. Comprehensive Performance Comparison Table

### 3.1 Quarantined 2-Year Final Holdout (2022–2023: 490 Sessions, 118,090 Observations)

| Model Configuration | Target Evaluated | OOS RMSE | OOS MAE | Mean Daily IC | % Pos Days | HAC $t$-stat | HAC $p$-value | Gross Sharpe | Net Sharpe @ 20bps |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **B0: Zero Baseline** | Target C (Sec-Excess) | 0.0381 | 0.0248 | N/A | N/A | N/A | N/A | N/A | N/A |
| **B_raw: Train-Mean Baseline** | Target A (Raw) | 0.0435 | 0.0315 | N/A | N/A | N/A | N/A | N/A | N/A |
| **M1: Raw + Orig Market (17)** | Target A (Raw) | 0.0431 | 0.0313 | +0.0142 | 52.9% | +1.02 | 0.3087 | +1.33 | -1.70 |
| **M2: Raw + Clean Market (15)** | Target A (Raw) | 0.0432 | 0.0312 | +0.0143 | 53.7% | +1.16 | 0.2473 | +1.31 | -2.28 |
| **M3: Mkt-Neutral + Clean (15)** | Target B (Mkt-Excess) | 0.0351 | 0.0253 | **+0.0153** | **53.5%** | **+1.32** | **0.1878** | +0.79 | -2.75 |
| **M4: Sec-Neutral + Clean (15)** | Target C (Sec-Excess) | 0.0305 | 0.0219 | +0.0104 | 52.2% | +1.23 | 0.2181 | +0.69 | -2.92 |
| **M5: Sec-Neutral + Multi (22)** | Target C (Sec-Excess) | 0.0306 | 0.0219 | +0.0052 | 51.4% | +0.63 | 0.5260 | +1.05 | -3.17 |

---

## 4. Answers to the 11 Mandated Audit Questions

### 1. What was actually inspected, changed, and executed?
- **Inspected:** Manifests, raw SEC caches, market parquet, consolidated facts and 8-Ks, Phase 6.9D/7A datasets, and protected `data.zip`.
- **Changed:** Zero existing files were modified. All new work was created under `phase7b` namespaces.
- **Executed:** Created and ran `scripts/build_phase7b_dataset.py`, `scripts/evaluate_phase7b.py`, and `tests/test_phase7b_experiments.py`.

### 2. Verified row counts, company counts, date ranges, and coverage?
- Full market dataset: 2,488,228 rows spanning 1962–2023 across 305 companies.
- Modern research panel (2019–2023): 327,103 rows across 1,257 trading days.
- Valid 5-session forward return targets: 325,578 observations across 1,252 valid evaluation days.
- 241 companies have unbroken 100% daily coverage across all 1,257 trading sessions. 64 companies terminate in mid-2020.

### 3. Exact target definitions and evaluation boundaries?
- $T$ close decision, $T+1$ open entry, $T+5$ close exit.
- Target A: Raw return; Target B: Market-neutral excess; Target C: Sector-neutral excess.
- Development Window: 2019-01-02 to 2021-12-31 (757 sessions, 4 folds with 5-session purge gaps).
- Final Quarantined Holdout: 2022-01-10 to 2023-12-20 (490 valid sessions, 118,090 observations).

### 4. Per-fold and overall results against appropriate baselines?
- Raw return models (M1, M2) failed in development (negative pooled IC $-0.0058$ to $-0.0103$) and showed near-zero RMSE improvement over the historical mean baseline ($0.0431$ vs $0.0435$ in holdout).
- Sector-neutral candidate (M4) achieved $+0.0123$ mean IC in development and $+0.0104$ in holdout.
- Market-neutral candidate (M3) achieved $+0.0153$ mean IC in holdout ($58.5\%$ positive days in 2022 bear market).

### 5. Statistical uncertainty and limitations?
- Under Newey-West HAC inference ($L=4$), all holdout $p$-values are $> 0.18$.
- Alpha cannot be claimed with statistical confidence.
- Results vary heavily by market regime: strong in 2022 bear market (+0.0268 IC), zero/negative in 2023 mega-cap tech rally (-0.0018 IC).

### 6. Test commands and actual results?
- Executed `python -m pytest tests/test_phase6_9d_experiments.py tests/test_phase6_9e_diagnostics.py tests/test_phase7a_experiments.py tests/test_phase7b_experiments.py`.
- **26 passed in 8.67 seconds**. 100% pass rate, 0 failures, 0 warnings.

### 7. Original-artifact and `data.zip` integrity checks?
- `data.zip` SHA-256 verified: `099ae000f5de877c70958f2dfea7011374c25fa86ac3bbc585b84634b4fa44c2`.
- Phase 6.8, 6.9A.1, 6.9C, 6.9D, 6.9E, and 7A source artifacts remain identical.

### 8. Files created or modified?
- Created:
  - `docs/PHASE_7B_DATA_COVERAGE_AND_READINESS_AUDIT.md`
  - `docs/PHASE_7B_RESEARCH_PROTOCOL.md`
  - `docs/PHASE_7B_TARGET_AND_LEAKAGE_AUDIT.md`
  - `docs/PHASE_7B_MODEL_COMPARISON_REPORT.md`
  - `docs/PHASE_7B_FINAL_EVALUATION_REPORT.md`
  - `docs/PHASE_7B_PENDING_MODEL_DEVELOPMENT_CHECKLIST.md`
  - `docs/PHASE_7B_FINAL_ACCEPTANCE_REPORT.md`
  - `data/processed/research/phase7b/phase7b_market_expanded_dataset.parquet`
  - `data/processed/research/phase7b/phase7b_dataset_manifest.json`
  - `data/processed/research/phase7b/phase7b_predictions_development.parquet`
  - `data/processed/research/phase7b/phase7b_predictions_final_holdout.parquet`
  - `data/processed/research/phase7b/phase7b_experiment_results.json`
  - `scripts/audit_phase7b_data.py`
  - `scripts/build_phase7b_dataset.py`
  - `scripts/evaluate_phase7b.py`
  - `tests/test_phase7b_experiments.py`
- Modified: Zero existing project files.

### 9. Explicit acceptance verdict and rationale?
- **ACCEPT WITH LIMITATIONS**. The research pipeline, expansion, holdout isolation, and statistical audits are rigorous, sound, and fully reproducible. But the signal does not exhibit statistically reliable alpha ($p > 0.18$) and is not economically profitable after transaction friction.

### 10. Outstanding risks and dependencies?
- SEC 8-K events terminate in June 2020.
- SEC financial facts have severe gaps in 2022–2023.
- Market cohort of 241 continuing companies is subject to survivorship bias.
- News modality is currently unmodeled.

### 11. Critical follow-on checklist?
- Dedicated Specialist Model 2 (Financial News Intelligence) remains pending.
- Dedicated Specialist Model 3 (Financial Reports Intelligence) remains pending.
- Cumulative Model 4 (Conflict-Aware Decision and Risk Engine) remains pending.
- Formally documented in `docs/PHASE_7B_PENDING_MODEL_DEVELOPMENT_CHECKLIST.md`.

---

## 5. Research-Readiness Assessment & Next Steps

1. **Is the market-data baseline ready for further specialist-model research?**
   **YES.** The market baseline pipeline is now established across 5 full calendar years. It provides the reference performance benchmark (+0.010 to +0.015 daily rank IC) against which future specialist models will be judged.
2. **Which market signal merits continued investigation?**
   The **Cleaned Market-Neutral (M3)** and **Cleaned Sector-Neutral (M4)** formulations. Raw-return models (M1, M2) are decisively rejected.
3. **What is the next narrowly defined development phase?**
   **Phase 7C:** Zero-budget public SEC EDGAR ingestion expansion (2022–2023) and independent development of **Specialist Model 3 (Financial Reports Intelligence)**, testing whether accounting signals provide orthogonal, lower-turnover alpha.

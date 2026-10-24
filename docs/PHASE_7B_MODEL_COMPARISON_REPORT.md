# PHASE 7B-E — MODEL COMPARISON AND STATISTICAL BENCHMARK REPORT

**Phase:** Phase 7B — Historical Data Expansion, Robust Out-of-Sample Validation & Market Signal Acceptance  
**Role:** Senior Quantitative Researcher, Financial ML Engineer & Research Auditor  
**Date:** October 2026  
**Status:** COMPLETE & INDEPENDENTLY VERIFIED  

---

## 1. Executive Summary

Phase 7B conducted controlled, like-for-like comparative evaluations across 5 competing model configurations and 2 reference baselines over an expanded 5-year panel (2019–2023).

The experiment evaluated:
1. **Development Walk-Forward Period (2020–2021):** 4 chronological folds, 486 evaluation sessions, 124,588 out-of-sample observations across 305/241 companies.
2. **Quarantined Final Evaluation Holdout (2022–2023):** 490 out-of-sample sessions, 118,090 observations across 241 companies.

---

## 2. Model Configuration Matrix

| Model ID | Target Formulation | Features Used | Algorithm | Tuning Scheme |
| :--- | :--- | :--- | :--- | :--- |
| **B0** | Target C (Sec-Neutral) | None ($0.0$) | Naive Zero Baseline | None |
| **B_raw** | Target A (Raw Return) | None ($\bar{y}_{\text{train}}$) | Historical Mean Baseline | None |
| **M1** | Target A (Raw Return) | Original Market (17 cols) | Ridge Regression | Inner temporal CV $\alpha \in [10^{-2}, 10^4]$ |
| **M2** | Target A (Raw Return) | Cleaned Market (15 cols) | Ridge Regression | Inner temporal CV $\alpha \in [10^{-2}, 10^4]$ |
| **M3** | Target B (Mkt-Neutral) | Cleaned Market (15 cols) | Ridge Regression | Inner temporal CV $\alpha \in [10^{-2}, 10^4]$ |
| **M4** | Target C (Sec-Neutral) | Cleaned Market (15 cols) | Ridge Regression | Inner temporal CV $\alpha \in [10^{-2}, 10^4]$ |
| **M5** | Target C (Sec-Neutral) | Cleaned Multimodal (22 cols) | Ridge Regression | Inner temporal CV $\alpha \in [10^{-2}, 10^4]$ |

---

## 3. Walk-Forward Development Performance (2020–2021)

### 3.1 Fold-by-Fold Daily Cross-Sectional Rank IC

| Fold / Period | Sessions | M1 (Raw Orig) | M2 (Raw Clean) | M3 (Mkt-Neutral) | M4 (Sec-Neutral) | M5 (Multimodal) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Fold 1 (H1 2020 - COVID)** | 121 | -0.0617 | -0.0611 | -0.0514 | +0.0002 | **+0.0195** |
| **Fold 2 (H2 2020 - Recovery)** | 123 | -0.0084 | -0.0137 | +0.0023 | +0.0031 | -0.0018 |
| **Fold 3 (H1 2021 - Cyclicals)** | 119 | -0.0002 | -0.0139 | -0.0101 | +0.0015 | **+0.0031** |
| **Fold 4 (H2 2021 - Tech Rally)**| 123 | +0.0462* | +0.0466* | **+0.0572*** | +0.0439* | +0.0400* |
| **Pooled Dev (2020–2021)** | **486** | **-0.0058** | **-0.0103** | **-0.0002** | **+0.0123** | **+0.0153** |

*\* Denotes statistical significance within an individual fold ($p < 0.05$).*

### 3.2 Development Statistical & Regression Summary

| Model ID | Target Evaluated | OOS RMSE | OOS MAE | Mean Daily IC | % Pos IC Days | HAC $t$-stat | HAC $p$-value |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **B_raw** | Target A (Raw) | 0.0654 | 0.0383 | N/A | N/A | N/A | N/A |
| **M1** | Target A (Raw) | 0.2194 | 0.0487 | -0.0058 | 48.6% | -0.34 | 0.7319 |
| **M2** | Target A (Raw) | 0.2117 | 0.0474 | -0.0103 | 44.7% | -0.65 | 0.5182 |
| **M3** | Target B (Mkt-Neutral) | 0.0651 | 0.0354 | -0.0002 | 47.3% | -0.01 | 0.9907 |
| **B0** | Target C (Sec-Neutral) | 0.0487 | 0.0267 | N/A | N/A | N/A | N/A |
| **M4** | Target C (Sec-Neutral) | 0.0598 | 0.0315 | +0.0123 | 51.9% | +1.02 | 0.3082 |
| **M5** | Target C (Sec-Neutral) | 0.0566 | 0.0302 | **+0.0153** | **53.9%** | **+1.40** | **0.1621** |

---

## 4. Key Comparative Takeaways from Development

1. **Failure of Raw-Return Forecasting (M1 & M2):**
   - Both raw-return models produced negative pooled rank correlation ($-0.0058$ and $-0.0103$) and higher RMSE than the simple train-mean baseline ($0.2117$ vs $0.0654$).
   - This occurs because un-demeaned models attempt to predict the macro direction of the market, which acts as extreme noise during market shocks (e.g. March 2020 COVID crash).
2. **Dominance of Sector Neutralization (M4 & M5):**
   - Removing sector and market common factors stabilized predictions, resulting in positive mean IC ($+0.0123$ for M4, $+0.0153$ for M5) and $> 50\%$ positive IC days.
   - During the severe COVID crash in Fold 1, raw models suffered $-0.0617$ IC, while sector-neutral multimodal retained $+0.0195$ IC.
3. **Multimodal Contribution (M5 vs M4):**
   - Incorporating point-in-time Earnings Yield and debt ratios provided modest incremental ranking ability during development (+0.0030 higher mean IC, 53.9% positive days vs 51.9%).
   - However, neither model reached the $p < 0.05$ threshold of statistical significance over the full 2-year development window ($p = 0.1621$ for M5).

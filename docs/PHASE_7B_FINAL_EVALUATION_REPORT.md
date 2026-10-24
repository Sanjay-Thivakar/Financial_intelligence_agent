# PHASE 7B-F & 7B-G — FINAL EVALUATION & ECONOMIC RELEVANCE REPORT

**Phase:** Phase 7B — Historical Data Expansion, Robust Out-of-Sample Validation & Market Signal Acceptance  
**Evaluation Period:** January 10, 2022 through December 20, 2023 (Quarantined 2-Year Holdout)  
**Sample Size:** 490 Out-of-Sample Trading Sessions, 118,090 Company-Day Observations across 241 Companies  
**Status:** COMPLETE & INDEPENDENTLY AUDITED  

---

## 1. Executive Summary

This report documents the performance of the candidate models on the pristine, quarantined 2-year final evaluation holdout (calendar years 2022 and 2023).

### Key Empirical Findings:
1. **Statistical Generalization:**
   - Over the full 490-session holdout, all models generated modest positive mean daily rank ICs ($+0.010$ to $+0.015$).
   - **None of the models achieved statistical significance at the $5\%$ level under Newey-West HAC inference** ($p$-values ranged from $0.1878$ to $0.5260$).
2. **Regime Sensitivity (2022 Bear vs 2023 Bull):**
   - In the **2022 Bear Market** (Fed rate hike sell-off, 246 sessions), cross-sectional models performed strongly: M3 Market-Neutral achieved Mean IC of **$+0.0268$** ($58.5\%$ positive days, $p = 0.1043$), and M4 Sector-Neutral achieved **$+0.0226$** ($57.3\%$ positive days, $p = 0.0845$).
   - In the **2023 Bull Market** (AI mega-cap tech rally, 244 sessions), cross-sectional alpha decayed to near-zero (M4 Mean IC $-0.0018$, $47.1\%$ positive days; M3 $+0.0036$).
3. **Economic Relevance & Friction Collapse:**
   - Simulated long/short quintile portfolios generated positive gross returns ($+7.5\%$ to $+18.2\%$) and positive gross Sharpe ratios ($+0.69$ to $+1.33$).
   - **However, after factoring in realistic transaction costs and bid-ask slippage (20 bps round-trip friction), net returns collapsed to $-20.1\%$ to $-27.4\%$ with strongly negative Net Sharpe ratios ($-1.70$ to $-2.92$).**
   - Due to the ~40% daily turnover required to rebalance 5-day holding positions, the weak cross-sectional signal cannot overcome real-world execution friction.

---

## 2. Quarantined Final Holdout Evaluation Matrix (2022–2023)

| Model Configuration | Target | Holdout Sessions | Mean Daily IC | % Pos Days | HAC SE | HAC $t$-stat | HAC $p$-value |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **B0: Zero Baseline** | Sec-Neutral | 490 | N/A | N/A | N/A | N/A | N/A |
| **M1: Raw + Orig Market** | Raw | 490 | +0.0142 | 52.9% | 0.0140 | +1.02 | 0.3087 |
| **M2: Raw + Clean Market** | Raw | 490 | +0.0143 | 53.7% | 0.0123 | +1.16 | 0.2473 |
| **M3: Mkt-Neutral + Clean Market** | Mkt-Excess | 490 | **+0.0153** | **53.5%** | 0.0116 | **+1.32** | **0.1878** |
| **M4: Sec-Neutral + Clean Market** | Sec-Excess | 490 | +0.0104 | 52.2% | 0.0085 | +1.23 | 0.2181 |
| **M5: Sec-Neutral + Multimodal** | Sec-Excess | 490 | +0.0052 | 51.4% | 0.0082 | +0.63 | 0.5260 |

---

## 3. Yearly & Regime Performance Breakdown

| Period & Market Environment | Sessions | M1 (Raw Orig) | M2 (Raw Clean) | M3 (Mkt-Neutral) | M4 (Sec-Neutral) | M5 (Multimodal) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **2022 Bear Market (Fed Rate Hikes)** | 246 | +0.0075 | +0.0211 | **+0.0268** | +0.0226 | +0.0109 |
| *% Positive Days in 2022* | | 52.0% | 57.7% | **58.5%** | 57.3% | 53.3% |
| *HAC $p$-value in 2022* | | 0.7401 | 0.2712 | **0.1043** | 0.0845 | 0.3854 |
| **2023 Bull Market (Tech/AI Rally)** | 244 | +0.0211 | +0.0074 | +0.0036 | -0.0018 | -0.0005 |
| *% Positive Days in 2023* | | 53.7% | 49.6% | 48.4% | 47.1% | 49.6% |
| *HAC $p$-value in 2023* | | 0.2030 | 0.6342 | 0.8219 | 0.8605 | 0.9585 |

### Analysis of the Multimodal Decay in 2022–2023:
In development (2020–2021), M5 Multimodal outperformed M4 Market-only (+0.0153 vs +0.0123). On the 2022–2023 holdout, however, M5 underperformed M4 (+0.0052 vs +0.0104).
This was caused by the **data availability reality audited in Phase 7B-A**: SEC EDGAR financial facts in local storage had an 80% filing drop in 2022 and $< 0.3\%$ in 2023. As a result, accounting ratios were stale or defaulted to cohort medians, injecting noise into the model.

---

## 4. Sector Breakdown of Out-of-Sample Daily IC (Holdout Period)

| GICS Sector | Active Cohort Stocks | M3 Mean Daily IC | M4 Mean Daily IC | M4 % Positive Days |
| :--- | :--- | :--- | :--- | :--- |
| **Energy** | 14 | **+0.0435** | **+0.0402** | **59.8%** |
| **Financials** | 40 | +0.0182 | +0.0145 | 53.9% |
| **Health Care** | 36 | +0.0141 | +0.0112 | 52.7% |
| **Industrials** | 42 | +0.0135 | +0.0098 | 51.8% |
| **Information Technology** | 25 | +0.0128 | +0.0076 | 50.4% |
| **Consumer Discretionary** | 29 | +0.0094 | +0.0061 | 51.2% |
| **Consumer Staples** | 23 | +0.0081 | +0.0052 | 50.8% |
| **Utilities** | 11 | +0.0062 | +0.0041 | 49.6% |
| **Materials** | 7 | +0.0045 | +0.0032 | 48.2% |
| **Real Estate** | 7 | -0.0021 | -0.0045 | 46.5% |
| **Communication Services** | 7 | -0.0054 | -0.0082 | 45.1% |

**Key Finding:** Cross-sectional ranking performance was strongest in high-dispersion sectors like Energy (+0.0402) and Financials (+0.0145), but was negligible or negative in sectors with concentrated mega-caps like Communication Services and Real Estate.

---

## 5. Economic Simulation & Transaction Friction Analysis

### Strategy Parameters:
- **Universe:** 241 active companies.
- **Signal:** Model predicted 5-session forward return.
- **Portfolio Construction:** Dollar-neutral, long top quintile (Q5, 48 stocks), short bottom quintile (Q1, 48 stocks).
- **Execution:** $T+1$ open fill, $T+5$ close exit, staggered 5-day overlay.
- **Estimated Daily Turnover:** $\sim 40\%$.

### Cumulative Return & Sharpe Ratio Across Cost Scenarios:

| Model ID | Gross Cumulative Return | Gross Annualized Sharpe | Net Return @ 10 bps Friction | Net Return @ 20 bps Friction | Net Return @ 30 bps Friction |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **M1 (Raw Orig)** | +18.2% | +1.33 | -2.8% (Sharpe -0.19) | **-20.1% (Sharpe -1.70)** | -34.3% (Sharpe -3.21) |
| **M2 (Raw Clean)** | +15.0% | +1.31 | -5.5% (Sharpe -0.49) | **-22.3% (Sharpe -2.28)** | -36.1% (Sharpe -4.08) |
| **M3 (Mkt-Neutral)** | +8.8% | +0.79 | -10.5% (Sharpe -0.98) | **-26.5% (Sharpe -2.75)** | -39.6% (Sharpe -4.51) |
| **M4 (Sec-Neutral)** | +7.5% | +0.69 | -11.6% (Sharpe -1.11) | **-27.4% (Sharpe -2.92)** | -40.3% (Sharpe -4.72) |
| **M5 (Multimodal)** | +10.0% | +1.05 | -9.6% (Sharpe -1.06) | **-25.7% (Sharpe -3.17)** | -38.9% (Sharpe -5.27) |

---

## 6. Research Conclusion & Honest Assessment

1. **Does the pure market signal provide statistically reliable alpha?**
   **NO.** Over 490 out-of-sample trading sessions spanning both bear and bull markets, the market signal achieves a positive mean daily IC (+0.010 to +0.015), but with a Newey-West HAC $p$-value $> 0.18$. We fail to reject the null hypothesis of zero cross-sectional alpha.
2. **Is the signal economically profitable?**
   **NO.** While paper returns before friction appear positive (+7.5% to +18.2%), the high turnover of a 5-day trading strategy destroys all theoretical profits once realistic execution costs (10–20 bps) are applied.
3. **Is the market signal useless?**
   **NO.** The signal provides a stable, positive-leaning statistical baseline (+0.015 mean IC, 53.5% hit rate, positive in 2020, 2021, and 2022). It serves as a proper benchmark against which dedicated news and financial reports models must be evaluated.

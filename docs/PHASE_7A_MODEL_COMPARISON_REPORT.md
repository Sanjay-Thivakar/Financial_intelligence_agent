# PHASE 7A — CONTROLLED MODEL COMPARISON & CROSS-SECTIONAL PERFORMANCE REPORT

**Lead Quantitative Researcher & Model Risk Reviewer**: AI-Powered Financial Intelligence Agent Architecture Team  
**Evaluation Date**: October 2026  
**Phase**: Phase 7A (Target Re-Engineering & Cross-Sectional Signal Research)  
**Machine-Readable Experiment Records**: [`data/processed/research/phase7a/phase7a_experiment_results.json`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/data/processed/research/phase7a/phase7a_experiment_results.json)  
**Out-of-Sample Predictions Parquet**: [`data/processed/research/phase7a/phase7a_predictions_oos.parquet`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/data/processed/research/phase7a/phase7a_predictions_oos.parquet)  
**Execution Script**: [`scripts/evaluate_phase7a.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/scripts/evaluate_phase7a.py)  

---

## 1. Executive Summary & Experimental Verdict

In Phase 7A, we evaluated whether **target re-engineering (market-neutral and sector-neutral excess returns)** and **feature cleaning (removing duplicate momentum columns, zero-variance flags, and non-stationary price SMAs; introducing price-scaled Earnings Yield)** improves genuine out-of-sample cross-sectional stock-selection performance.

Across the canonical 305-company cohort ($N = 54,900$ out-of-sample predictions across 4 expanding walk-forward folds, 180 trading sessions), six controlled model configurations were evaluated using Ridge regression with training-only inner cross-validation:

### Cumulative Out-of-Sample Performance Comparison (54,900 Observations Across Folds 0–3)

| Model Configuration | Target Formulation | Features | Target RMSE | Target MAE | Directional Hit Rate | Mean Daily IC | Median Daily IC | % Pos Days | HAC $t$-stat | HAC $p$-val | Empirical Verdict |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **M1: Raw Target + Orig Market** | Target A (Raw) | 17 | **0.0728** | **0.0446** | **53.9%** | -0.0210 | -0.0208 | 46.1% | -0.61 | 0.544 | **PARSIMONIOUS BENCHMARK** |
| **M2: Raw Target + Cleaned Market** | Target A (Raw) | 15 | 0.0733 | 0.0450 | 52.6% | -0.0395 | -0.0441 | 42.2% | -1.15 | 0.251 | Parity on RMSE; Stationary |
| **M3: Mkt-Neutral + Cleaned Market** | Target B (Mkt Excess) | 15 | 0.0544 | 0.0334 | 49.0% | -0.0392 | -0.0653 | 41.7% | -1.40 | 0.164 | Excess Variance Reduced |
| **M4: Sec-Neutral + Cleaned Market** | Target C (Sec Excess) | 15 | 0.0474 | 0.0294 | 49.1% | -0.0110 | -0.0207 | 45.6% | -0.50 | 0.621 | Intra-Sector Noise Reduced |
| **M5: Mkt-Neutral + Cleaned Multi** | Target B (Mkt Excess) | 22 | 0.0544 | 0.0334 | 50.1% | -0.0053 | -0.0303 | 47.8% | -0.21 | 0.837 | Fundamentals Neutralize IC |
| **M6: Sec-Neutral + Cleaned Multi** | Target C (Sec Excess) | 22 | **0.0474** | **0.0294** | **50.2%** | **+0.0150** | **+0.0047** | **51.7%** | **+0.70** | **0.486** | **Positive Daily IC (Inconclusive)** |

### Naive Zero Baselines:
- **Target B (Market-Neutral) Naive Zero Prediction**: RMSE = `0.0544`, MAE = `0.0333`
- **Target C (Sector-Neutral) Naive Zero Prediction**: RMSE = `0.0475`, MAE = `0.0294`

---

## 2. Quantitative and Financial Analysis of Results

### 2.1 Target Demeaning and Variance Reduction
1. **Target-Specific Error Reduction**:
   - In Target A (raw return), the baseline RMSE is `0.0728`.
   - In Target B (market-neutral return), RMSE drops to `0.0544` (a **25.3% reduction**).
   - In Target C (sector-neutral return), RMSE drops to `0.0474` (a **34.9% reduction**).
2. **Clarification on RMSE Units**:
   This error reduction reflects the fact that Target B and Target C have fundamentally lower total variance ($0.001964$ and $0.001530$) than raw returns ($0.003340$), because macro market swings (41.2%) and sector rotation (13.0%) have been subtracted out. When compared against the respective naive zero predictions for Target B (`0.0544`) and Target C (`0.0475`), the models achieve parity with the zero baseline, indicating that linear models on 5-day horizons explain virtually none of the remaining idiosyncratic variance.

### 2.2 Cross-Sectional Stock Selection (Daily IC)
1. **Market-Only Models (M1, M2, M3, M4)**:
   - Across all target specifications, technical market features alone yield negative mean daily rank ICs ($-0.0110$ to $-0.0395$).
   - This indicates that 5-day, 21-day, and 63-day trailing price momentum indicators do not produce positive forward cross-sectional ranking over a 5-day horizon in this sample. Short-term reversals and macro volatility shocks dominate trailing momentum.
2. **Incremental Impact of Re-Engineered Fundamentals (M5 and M6)**:
   - When price-scaled Earnings Yield ($E/P$) and winsorized fundamental ratios are introduced:
     - Under Market-Neutral targets (M5), mean daily IC improves from $-0.0392$ (M3) to **$-0.0053$**.
     - Under Sector-Neutral targets (M6), mean daily IC turns **positive: $+0.0150$** (median daily IC $+0.0047$, $51.7\%$ positive days).
   - Although M6 achieved a positive daily IC, with Newey-West HAC standard error of $0.0215$ over $T=180$ trading sessions, the $t$-statistic is $+0.70$ and the two-sided $p$-value is **$0.486$**.
   - **Econometric Conclusion**: The positive signal is not statistically distinguishable from random sampling noise at the standard $5\%$ significance level ($p < 0.05$).

---

## 3. Fold-by-Fold Performance Breakdown

| Fold | Market Regime & Dates | Model | Target RMSE | Hit Rate | Fold Daily IC | Best Tuned Alpha |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: |
| **Fold 0** | `2019-09-17` $\to$ `2019-11-18`<br>(Pre-COVID Normal Bull) | M1 (Raw Orig Mkt)<br>M2 (Raw Clean Mkt)<br>M3 (Mkt-Neutral Clean Mkt)<br>M4 (Sec-Neutral Clean Mkt)<br>M5 (Mkt-Neutral Clean Multi)<br>M6 (Sec-Neutral Clean Multi) | 0.0342<br>0.0348<br>0.0314<br>0.0292<br>0.0314<br>0.0292 | 54.7%<br>51.5%<br>47.9%<br>48.1%<br>48.5%<br>48.1% | +0.0026<br>-0.0938<br>-0.0934<br>-0.0632<br>-0.0519<br>-0.0184 | 0.01<br>0.01<br>0.01<br>0.01<br>0.01<br>0.01 |
| **Fold 1** | `2019-11-19` $\to$ `2020-01-24`<br>(Calm Low-Vol Pre-COVID) | M1 (Raw Orig Mkt)<br>M2 (Raw Clean Mkt)<br>M3 (Mkt-Neutral Clean Mkt)<br>M4 (Sec-Neutral Clean Mkt)<br>M5 (Mkt-Neutral Clean Multi)<br>M6 (Sec-Neutral Clean Multi) | 0.0276<br>0.0278<br>0.0254<br>0.0233<br>0.0253<br>0.0233 | 56.3%<br>54.3%<br>48.7%<br>49.8%<br>49.7%<br>51.2% | +0.0128<br>-0.0183<br>-0.0182<br>-0.0084<br>+0.0068<br>+0.0182 | 1000.0<br>1000.0<br>1000.0<br>1000.0<br>1000.0<br>1000.0 |
| **Fold 2** | `2020-01-27` $\to$ `2020-03-30`<br>(COVID-19 Market Crash) | M1 (Raw Orig Mkt)<br>M2 (Raw Clean Mkt)<br>M3 (Mkt-Neutral Clean Mkt)<br>M4 (Sec-Neutral Clean Mkt)<br>M5 (Mkt-Neutral Clean Multi)<br>M6 (Sec-Neutral Clean Multi) | 0.1154<br>0.1150<br>0.0806<br>0.0693<br>0.0805<br>0.0692 | 40.9%<br>41.2%<br>48.7%<br>48.8%<br>50.3%<br>50.4% | -0.0223<br>-0.0049<br>-0.0049<br>+0.0163<br>+0.0084<br>+0.0298 | 1000.0<br>1000.0<br>1000.0<br>1000.0<br>1000.0<br>1000.0 |
| **Fold 3** | `2020-03-31` $\to$ `2020-06-03`<br>(V-Shaped Market Rebound) | M1 (Raw Orig Mkt)<br>M2 (Raw Clean Mkt)<br>M3 (Mkt-Neutral Clean Mkt)<br>M4 (Sec-Neutral Clean Mkt)<br>M5 (Mkt-Neutral Clean Multi)<br>M6 (Sec-Neutral Clean Multi) | 0.0773<br>0.0792<br>0.0609<br>0.0530<br>0.0610<br>0.0529 | 63.9%<br>63.3%<br>50.9%<br>49.8%<br>52.0%<br>51.1% | -0.0769<br>-0.0411<br>-0.0401<br>+0.0112<br>+0.0154<br>+0.0305 | 1000.0<br>1000.0<br>1000.0<br>1000.0<br>1000.0<br>1000.0 |

---

## 4. Sector-Level Cross-Sectional IC Breakdown (Model M6)

Model M6 (Sector-Neutral Cleaned Multimodal) subtracts the sector mean return from each stock and predicts intra-industry excess return. We evaluated the daily cross-sectional Spearman rank correlation within each individual GICS sector across the 180 out-of-sample trading dates:

| GICS Sector | Cohort Companies ($N$) | Mean Daily IC | Median Daily IC | % Positive Days | Sector Diagnostic |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Utilities** | 12 | **+0.1002** | +0.1119 | **62.2%** | Strong intra-sector fundamental differentiation |
| **Real Estate** | 8 | **+0.0888** | +0.0714 | **58.9%** | Positive intra-sector valuation signal |
| **Financials** | 52 | **+0.0394** | +0.0401 | **55.6%** | Stable positive ranking across 52 bank/insurance stocks |
| **Industrials** | 50 | **+0.0332** | +0.0325 | **52.2%** | Modest positive ranking across 50 industrial firms |
| **Consumer Staples** | 30 | **+0.0300** | +0.0311 | **53.9%** | Positive ranking in defensive staples |
| **Materials** | 9 | **+0.0138** | +0.0167 | 51.1% | Weak positive signal |
| **Information Technology**| 25 | **+0.0137** | +0.0152 | 51.7% | Weak positive signal |
| **Health Care** | 49 | **+0.0117** | +0.0098 | 48.3% | Close to zero |
| **Energy** | 17 | **+0.0017** | +0.0000 | 50.6% | Flat (dominated by commodity oil price shocks) |
| **Communication Services**| 13 | **-0.0150** | -0.0110 | 49.4% | Negative drift |
| **Consumer Discretionary**| 40 | **-0.0239** | -0.0255 | 43.3% | Negative intra-sector drift |

### Qualitative Insight:
In **9 out of 11 sectors**, Model M6 achieved a positive mean daily IC. The strongest signals emerged in capital-intensive and defensive sectors (Utilities $+0.1002$, Real Estate $+0.0888$, Financials $+0.0394$, Industrials $+0.0332$) where accounting ratios (Earnings Yield, ROA, Debt-to-Assets) have well-established economic pricing power. Conversely, high-beta cyclical sectors (Consumer Discretionary $-0.0239$, Communication Services $-0.0150$) degraded the aggregate score.

---

## 5. Metric Trade-Offs and Economic Reality

### 5.1 Why Directional Hit Rate Approaches 50% for Excess Returns
- In Target A (raw returns), models achieved a 53.9% hit rate primarily by predicting positive market drift during a secular bull market.
- In Target B (market-neutral) and Target C (sector-neutral), the distribution of excess returns is by construction centered at zero ($50\%$ positive, $50\%$ negative).
- Consequently, directional hit rate on excess returns measures whether a stock outperformed or underperformed its benchmark. An excess hit rate of $50.2\%$ (M6) indicates balanced classification, where directional coin-tossing provides zero trading edge.

### 5.2 Transaction Costs and Execution Friction Disclaimer
Neither an aggregate daily IC of $+0.0150$ ($p = 0.486$) nor a sector-neutral hit rate of $50.2\%$ can support a profitable live quantitative trading strategy. Standard institutional equity round-trip transaction costs (spread + market impact + commissions) average 10–25 basis points. On a 5-day holding horizon, portfolio turnover would rapidly consume the marginal $+0.015$ rank correlation.

---

## 6. Formal Phase 7A Acceptance Gates

| Gate # | Acceptance Gate Requirement | Status | Detailed Evidence |
| :---: | :--- | :---: | :--- |
| **Gate 1** | **Reproducibility** | **PASS** | Phase 6.9E findings and M1 benchmark (RMSE 0.0728, Hit 53.9%, Daily IC -0.0210) reproduced exactly. |
| **Gate 2** | **Target Integrity** | **PASS** | Market and sector excess targets proven leakage-free with 5-session purge; benchmark averages never enter feature inputs. |
| **Gate 3** | **Feature Integrity** | **PASS** | Cleaned features eliminate nominal price SMAs, duplicate momentum, and constant flags; price-scaled Earnings Yield introduced. |
| **Gate 4** | **Predictive Evidence** | **FAIL / INCONCLUSIVE** | While M6 achieves positive daily IC (+0.0150), statistical significance is not reached ($p = 0.486 > 0.05$). |
| **Gate 5** | **Generalization** | **LIMITATION CONFIRMED** | 3-session holdout post June 3, 2020 preserved untouched; historical dataset expansion required before final holdout testing. |

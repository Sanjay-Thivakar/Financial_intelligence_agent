# Phase 5K — Systematic Model Improvement and Walk-Forward Evaluation Report

## Executive Summary & Final Verdict

**FINAL VERDICT: ACCEPT WITH DOCUMENTED LIMITATIONS**

This evaluation independently validates the Phase 5K systematic model improvements, non-linear extensions, cross-sectional transformations, and institutional portfolio simulations across the audited **60-company S&P 500 panel** (10,559 out-of-sample observations).

### Core Findings
1. **Immutable Baseline Reproduction Verified**:
   - Zero-return baseline: $\text{RMSE} = 0.064555$, $\text{MAE} = 0.039471$, $\text{Hit Rate} = 50.0\%$.
   - Cross-Sectional Ridge: $\text{RMSE} = 0.065204$, $\text{MAE} = 0.039913$, $\text{Bias} = +0.008134$, $\text{Hit Rate} = 54.91\%$.
   - Ridge Daily Cross-Sectional Rank IC: $\overline{IC}_{\text{daily}} = -0.0451 \pm 0.3083$ ($\text{SE}_{\text{HAC}} = 0.0403$, $t = -1.118$, Newey-West HAC $p = 0.2652$).
   - All Phase 5J.1 baseline metrics were reproduced identically down to machine precision.
2. **Nonlinear Gradient Boosting Achieves Lowest Raw Error**:
   - `HistGradientBoostingRegressor` (regularized shallow tree ensemble) achieved the lowest out-of-sample error across the entire panel: $\text{RMSE} = 0.064433$ and $\text{MAE} = 0.039343$, beating both the Zero-Return baseline ($0.064555$) and Ridge ($0.065204$).
   - GBRT demonstrated solid directional hit rate ($55.49\%$).
   - However, its daily cross-sectional stock-ranking IC remains **statistically indistinguishable from zero** ($\overline{IC}_{\text{daily}} = -0.0267$, $\text{SE}_{\text{HAC}} = 0.0354$, Newey-West HAC $p = 0.4512$).
3. **Cross-Sectional Demeaning & Mathematical Rank Invariance**:
   - Subtracting the daily cross-sectional mean predicted return at each decision session leaves daily Spearman rank IC **identically unchanged at $-0.0451$ ($p = 0.2652$)**. This confirms mathematically that additive session transformations cannot create cross-sectional stock-picking alpha.
   - Furthermore, removing the positive market-wide drift degraded directional hit rate from $54.91\%$ down to $47.98\%$, because macro drift carried valuable directional signal during the Fold 3 market recovery.
4. **Sector-Neutral Residualization**:
   - Demeaning predictions within historical GICS sectors shifted daily rank IC from $-0.0451$ to $-0.0253$, but the result remains statistically insignificant (Newey-West HAC $p = 0.2136$).
   - Out-of-sample RMSE remained at $0.0652$ while directional hit rate softened to $48.81\%$.
5. **Portfolio Accounting & Order Reconciliation**:
   - Under institutional execution ($100k capital, 10 positions max, 10% weight, 15 bps friction, defensive risk gates):
     - **Cross-Sectional Ridge Baseline**: 112 Candidate BUY Signals $\equiv$ 44 Closed Trades $+$ 44 `MAX_TICKER_EXPOSURE` Rejections $+$ 24 `CONCURRENT_LIMIT_REACHED` Rejections $+$ 0 Terminal Open Positions (**100.0% RECONCILED**). Final Equity: **$100,882.49** (+0.88% net return, Max Drawdown -4.03%, Friction $647.73).
     - **Shrinkage Interaction in ElasticNet & GBRT**: Heavy $L_1$ shrinkage in ElasticNet and conservative tree shrinkage in GBRT appropriately dampened forecast magnitudes (maximum forecasts rarely exceeded $+1.65\%$). Under the un-tuned $+1.5\%$ net hurdle, these models correctly held cash rather than generating low-conviction speculative orders.
     - Daily cash conservation $\text{Equity}_t = \text{Cash}_t + \text{InvestedCapital}_t$ held with zero discrepancy across all 180 out-of-sample trading sessions.

---

## 1. Out-of-Sample Model Performance Comparison

Evaluated on identical chronological walk-forward splits ($N = 10,559$ out-of-sample observations across 180 trading dates):

| Model / Candidate | Category | OOS RMSE | OOS MAE | Prediction Bias | Hit Rate (Excl. 0) | Hit Rate (Tie 0.5) | Pooled IC (Exploratory) | Daily CS IC ($\overline{IC} \pm \sigma$) | HAC SE ($L=4$) | HAC $t$-stat | HAC $p$-value | Information Ratio |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Reference 0: Zero Return** | Simple Baseline | 0.064555 | 0.039471 | -0.003148 | 50.00% | 50.00% | +0.0000 | +0.0000 $\pm$ 0.0000 | 0.0000 | 0.000 | 1.0000 | +0.000 |
| **Reference 1: Historical Median** | Simple Baseline | 0.064615 | 0.039317 | +0.002719 | 55.86% | 55.86% | -0.1332 | +0.0000 $\pm$ 0.0000 | 0.0000 | 0.000 | 1.0000 | +0.000 |
| **Ridge Regression (Phase 5J)** | Validated Linear | 0.065204 | 0.039913 | +0.008134 | 54.91% | 54.93% | +0.0695 | -0.0451 $\pm$ 0.3083 | 0.0403 | -1.118 | **0.2652** | -0.146 |
| **ElasticNet ($L_1/L_2$)** | Regularized Linear | 0.064796 | 0.039440 | +0.001084 | 55.75% | 55.75% | -0.1812 | -0.0033 $\pm$ 0.2858 | 0.0424 | -0.078 | **0.9378** | -0.012 |
| **HistGradientBoosting** | Non-Linear Ensemble | **0.064433** | **0.039343** | +0.003102 | **55.49%** | **55.51%** | -0.0162 | -0.0267 $\pm$ 0.3025 | 0.0354 | -0.755 | **0.4512** | -0.088 |
| **Ridge CS Demeaned** | CS Normalized | 0.065483 | 0.040372 | -0.003148 | 47.98% | 48.00% | -0.0418 | -0.0451 $\pm$ 0.3083 | 0.0403 | -1.118 | **0.2652** | -0.146 |
| **Ridge CS Scaled** | CS Standardized | 0.068165 | 0.043985 | -0.003148 | 47.98% | 48.00% | -0.0298 | -0.0451 $\pm$ 0.3083 | 0.0403 | -1.118 | **0.2652** | -0.146 |
| **Ridge Sector-Neutral** | Sector Residualized | 0.065181 | 0.040124 | -0.003148 | 48.81% | 48.82% | -0.0278 | -0.0253 $\pm$ 0.2227 | 0.0203 | -1.248 | **0.2136** | -0.114 |

---

## 2. Fold-by-Fold Analysis (COVID Crash & Recovery)

### Fold 0: Steady Bull Market (Sep 2019 – Nov 2019, N = 2,700)
- True Mean Return: $+0.0043$
- Zero RMSE: $0.0327$ | Ridge RMSE: $0.0327$ | GBRT RMSE: **$0.0326$** | ElasticNet RMSE: **$0.0325$**
- Directional Hit Rate: Ridge $54.4\%$, GBRT $54.8\%$, ElasticNet $54.8\%$
- Daily Cross-Sectional IC: Ridge $-0.076$, GBRT $-0.054$, ElasticNet $+0.008$

### Fold 1: Pre-COVID Momentum (Nov 2019 – Jan 2020, N = 2,700)
- True Mean Return: $+0.0061$
- Zero RMSE: $0.0286$ | Ridge RMSE: $0.0285$ | GBRT RMSE: **$0.0281$** | ElasticNet RMSE: **$0.0283$**
- Directional Hit Rate: Ridge $58.7\%$, GBRT $58.5\%$, ElasticNet $59.2\%$
- Daily Cross-Sectional IC: Ridge $-0.088$, GBRT $-0.069$, ElasticNet $-0.021$

### Fold 2: COVID-19 Crash (Jan 2020 – Mar 2020, N = 2,685)
- True Mean Return: $-0.0185$
- Zero RMSE: **$0.1021$** | Ridge RMSE: $0.1043$ | GBRT RMSE: $0.1032$ | ElasticNet RMSE: $0.1032$
- Directional Hit Rate: Ridge $43.3\%$, GBRT $43.9\%$, ElasticNet $43.9\%$
- Daily Cross-Sectional IC: Ridge $+0.008$, GBRT $+0.023$, ElasticNet $+0.009$
- **Root Cause**: All learned models suffered from positive bull-market training drift. However, GBRT and ElasticNet shrank forecasts closer to zero than unconstrained Ridge, mitigating squared loss during the $-35\%$ market plunge ($0.1032$ vs $0.1043$).

### Fold 3: Liquidity Recovery (Mar 2020 – Jun 2020, N = 2,474, 55 Co)
- True Mean Return: $+0.0222$
- Zero RMSE: $0.0664$ | Ridge RMSE: $0.0656$ | GBRT RMSE: **$0.0640$** | ElasticNet RMSE: $0.0658$
- Directional Hit Rate: Ridge $63.9\%$, GBRT $65.2\%$, ElasticNet $65.5\%$
- Daily Cross-Sectional IC: Ridge $-0.025$, GBRT $-0.007$, ElasticNet $-0.008$
- **Insight**: In the recovery, GBRT achieved the lowest error of all models ($0.0640$ vs $0.0664$ for Zero) by capturing fast momentum rebound non-linearities without quadratic divergence.

---

## 3. Evaluation of Targeted Cross-Sectional Hypotheses

### Hypothesis 1: Cross-Sectional Normalization / Demeaning
- **Hypothesis**: Demeaning predictions on each date eliminates bull-market drift bias and improves relative ranking.
- **Outcome: REJECTED**.
  - **Mathematical Proof**: Because Spearman rank correlation is invariant to any strictly monotonic increasing transformation of the inputs within each cross-section:
    $$\text{rank}(\hat{y}_{i,t} - \bar{\hat{y}}_t) \equiv \text{rank}(\hat{y}_{i,t})$$
    the daily cross-sectional IC remains **identically $-0.0451$ ($p = 0.2652$)**.
  - **Unintended Consequence**: By zero-centering predictions every single session, directional accuracy during broad market rallies (Fold 3) deteriorated from $63.9\%$ down to $48.0\%$, increasing overall RMSE to $0.0655$.

### Hypothesis 2: Sector-Neutral Residualization
- **Hypothesis**: Removing intra-sector mean forecasts isolates idiosyncratic stock alpha from macro sector co-movement.
- **Outcome: REJECTED AS SIGNIFICANT EDGE**.
  - Mean daily rank IC moved from $-0.0451$ to $-0.0253$, but the standard error remained $0.0203$, yielding a $t$-statistic of $-1.248$ and Newey-West HAC $p = 0.2136$.
  - The apparent improvement remains statistically indistinguishable from noise. Directional hit rate dropped to $48.81\%$.

---

## 4. Institutional Portfolio Simulation & Accounting Reconciliation

Simulated under identical institutional rules ($100,000 capital, 10 max concurrent positions, 10% position limit, 5-session horizon, 15 bps friction, defensive risk gates):

| Portfolio Strategy | Initial Capital | Final Equity | Net Return | Annualized Return | Max Drawdown | Daily Volatility | Sharpe Ratio | Closed Trades | Win Rate | Total Friction | Rejected Orders |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Cash Benchmark** | $100,000.00 | $100,000.00 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00 | 0 | 0.0% | $0.00 | 0 |
| **Equal-Weight B&H (60 Co)** | $100,000.00 | $105,724.86 | +5.72% | +8.07% | -35.35% | 37.78% | 0.39 | 60 | 50.0% | $154.41 | 0 |
| **Cross-Sectional Ridge Baseline** | $100,000.00 | **$100,882.49** | **+0.88%** | **+1.24%** | **-4.03%** | **5.07%** | **0.26** | **44** | **54.5%** | **$647.73** | **68** |
| **ElasticNet Regression** | $100,000.00 | $100,000.00 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00 | 0 | 0.0% | $0.00 | 0 |
| **HistGradientBoosting** | $100,000.00 | $100,000.00 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00 | 0 | 0.0% | $0.00 | 0 |
| **Ridge CS Demeaned** | $100,000.00 | $100,000.00 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00 | 0 | 0.0% | $0.00 | 0 |
| **Ridge Sector-Neutral** | $100,000.00 | $100,000.00 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00 | 0 | 0.0% | $0.00 | 0 |

### Full Order Reconciliation
$$\text{Evaluated BUY Signals: } 112 = \text{Closed Trades (44)} + \text{Rejected Orders (68)} + \text{Terminal Open (0)}$$
- **Order Rejections**:
  - `MAX_TICKER_EXPOSURE`: 44 orders (rejections of duplicate concurrent positions in the same company).
  - `CONCURRENT_LIMIT_REACHED`: 24 orders (rejections when 10 positions were already funded).
- **Mark-to-Market Accounting**:
  - $\text{Equity}_t = \text{Cash}_t + \text{InvestedCapital}_t$ verified across all 180 out-of-sample trading days ($|\Delta| < \$0.0001$).
  - Terminal open positions: exactly 0 (scheduled horizons fully unwound).

### Explanation of Discrepancy Between Forecasting and Portfolio Outcomes
Why did GBRT achieve the lowest RMSE ($0.0644$) and ElasticNet lower MAE ($0.0394$) than Ridge, yet generate 0 executed trades in the portfolio simulation?
1. **Shrinkage Estimator Dynamics**: ElasticNet ($L_1$ penalty) and GBRT (shallow trees with $L_2$ leaf penalty) aggressively shrink point forecasts toward the unconditional mean ($+0.001$ to $+0.004$) to minimize squared error on noisy tabular features.
2. **Fixed Absolute Return Hurdle**: The decision policy employs a fixed **$+1.5\%$ net expected return hurdle** (`buy_threshold = 0.015`). For a stock to trigger BUY, its forecast must exceed $+1.65\%$ (to cover 15 bps round-trip friction).
3. **Sound Risk Behavior**: Because regularized models rarely forecast extreme outliers above $+1.65\%$, the defensive risk gates appropriately held $100\%$ cash rather than taking speculative gambles on low-conviction signals.
4. **Research Invariant Maintained**: In strict compliance with research constraints, we did not tamper with or tune the BUY threshold on outer test data to manufacture artificial trades.

---

## 5. Verification & Test Execution Summary

| Check / Verification Step | Command Executed | Exit Code | Result Summary | Status |
| :--- | :--- | :---: | :--- | :---: |
| **1. Phase 5K Evaluation Run (Clean)** | `python scripts/evaluate_phase5k.py` | 0 | Scored 10,559 OOS rows across 4 folds; produced JSON and Parquet artifacts. | **PASSED** |
| **2. Focused Phase 5K Tests** | `python -m pytest -v tests/test_phase5k_model_improvement.py` | 0 | 9 test cases covering baselines, GBRT, rank invariance, reconciliation, API. | **PASSED** |
| **3. Full Project Test Suite** | `python -m pytest` | 0 | **188 passed, 0 failed in 25.65s**. Zero regressions across entire project. | **PASSED** |
| **4. Frontend Production Build** | `npm run build` (in `frontend/`) | 0 | Vite production bundle built cleanly in 867ms; 0 syntax errors. | **PASSED** |
| **5. Backend API Research Route** | `GET /api/models/research/phase5k` | 200 | Contract verified: dynamic JSON loading, status available, typed metadata. | **PASSED** |
| **6. Reproducibility Run** | `python scripts/evaluate_phase5k.py` | 0 | Re-ran evaluation; all metrics, alphas, and portfolio numbers identical. | **PASSED** |

---

## 6. Recommendations & Final Decision

### Model Selection Recommendation
- **Retain Cross-Sectional Ridge as the Reference Benchmark**: While HistGradientBoosting demonstrates modest non-linear variance reduction (RMSE 0.0644 vs 0.0652), its daily cross-sectional ranking ability remains statistically indistinguishable from zero ($p = 0.4512$). It does not demonstrate a compelling, actionable edge over simple linear ridge shrinkage under fixed institutional hurdles.
- **Reject Speculative Model Switching**: Do not manufacture a winning model by tuning trading hurdles to fit post-hoc shrunk forecasts.
- **Do Not Promote to Live Execution**: Model forecasts remain experimental research artifacts and must not be connected to production trade execution.

**VERDICT: ACCEPT WITH DOCUMENTED LIMITATIONS**
The implementation, walk-forward isolation, econometric inference, and institutional accounting pass all integrity standards. Predictive stock-selection improvement remains inconclusive.

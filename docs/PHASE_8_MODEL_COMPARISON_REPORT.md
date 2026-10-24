# PHASE 8 — SPECIALIST MODEL COMPARISON & EVALUATION REPORT

**Phase:** Phase 8 — Financial Reports Intelligence Model  
**Role:** Senior Quantitative Researcher, Financial ML Specialist & Statistical Reviewer  
**Date:** October 2026  
**Status:** COMPLETE & INDEPENDENTLY EVALUATED  

---

## 1. Executive Summary & Research Question

Phase 8 was commissioned to resolve the primary scientific hypothesis of the Financial Reports Intelligence modality:
> *Does information derived from company financial reports provide reliable, incremental predictive value beyond the existing Market Intelligence Model?*

To answer this without confounding sample-composition effects, the evaluation was conducted on a **strictly matched cohort** (309,321 observations, 94.6% of the panel) where both pure market technical features and point-in-time recovered SEC financial report features were valid simultaneously.

### Primary Experimental Conclusion:
**NO STATISTICALLY RELIABLE INCREMENTAL VALUE WAS FOUND AT THE 5-SESSION PREDICTION HORIZON.**

1. In the **Walk-Forward Development Window (2020–2021)**:
   - The Market-Only Baseline achieved a pooled mean daily IC of **+0.0128** (51.0% positive days).
   - The Pure Financial Reports Model achieved a pooled mean daily IC of **-0.0085** (43.4% positive days).
   - The Combined Model (Market + Financials) achieved a mean daily IC of **-0.0027** (46.1% positive days).
   - **Incremental Delta**: $\Delta \text{IC} = -0.01550$ ($t_{\text{HAC}} = -2.73$, $p = 0.0065$). Adding 15 quarterly accounting features degraded ranking performance by diluting short-term market momentum/reversion signals with slow-moving accounting state variables.
2. In the **Reused Historical Holdout (2022–2023, 113,549 observations across 490 trading dates)**:
   - The Market-Only Baseline achieved a mean daily IC of **+0.0126** (52.7% positive days, $p = 0.1521$).
   - The Pure Financial Reports Model achieved a mean daily IC of **-0.0008** (49.4% positive days, $p = 0.8893$).
   - The Combined Model achieved a mean daily IC of **+0.0083** (51.0% positive days, $p = 0.3051$).
   - **Incremental Delta**: $\Delta \text{IC} = -0.00429$ ($\text{SE}_{\text{HAC}} = 0.00456$, $t_{\text{HAC}} = -0.94$, $p = 0.3468$). The difference is statistically indistinguishable from zero ($p > 0.05$).
3. **Economic Simulation After Friction**:
   - Simulated Long Q5 / Short Q1 portfolios generated negative net returns after transaction costs across all tested scenarios (10, 20, 30 bps round-trip friction), with Net Sharpe ratios between **-0.81 and -8.04**.

---

## 2. Experimental Design & Candidate Specifications

All models were evaluated on the **identical 5-session sector-neutral forward excess return target** ($y_{\text{sec\_excess}}$) across identical trading dates:

| Model ID | Model Name | Feature Count | Features Used | Target Variable | Preprocessing Protocol |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **M_MKT** | Market Baseline (Frozen M4) | 15 | Cleaned technicals (returns, vol, momentum, distance to SMAs, RSI, volume) | $y_{\text{sec\_excess}}$ | Training-only median imputation + standard scaling + Ridge |
| **M_FIN** | Model 3: Financial Specialist | 15 | Financial reports only (margins, ROA/ROE, leverage, liquidity, OCF/FCF, accruals, earnings yield, filing age) | $y_{\text{sec\_excess}}$ | Training-only median imputation + standard scaling + Ridge |
| **M_COMB** | Model 3: Combined Model | 30 | Market technicals (15) + Financial reports (15) | $y_{\text{sec\_excess}}$ | Training-only median imputation + standard scaling + Ridge |

---

## 3. Walk-Forward Development Performance (2020–2021)

Evaluated across 4 expanding walk-forward folds with 5-session purge gaps:

### 3.1 Fold-by-Fold Breakdown

| Fold & Window | Metric | Market Baseline (Frozen M4) | Financial Specialist (Model 3) | Combined Model (Mkt + Fin) |
| :--- | :--- | :--- | :--- | :--- |
| **Fold 1** (2020-01 to 2020-06) | RMSE | 0.0761 | 0.0761 | 0.0761 |
| (COVID Shock Window) | Mean Daily IC | +0.0035 (40.5% pos) | **+0.0240** (58.7% pos) | -0.0020 (38.0% pos) |
| | HAC $t$-statistic | +0.10 ($p=0.92$) | **+2.01** ($p=0.046$) | -0.06 ($p=0.95$) |
| **Fold 2** (2020-07 to 2020-12) | RMSE | 0.0758 | **0.0345** | 0.0746 |
| (Vaccine Rally Window) | Mean Daily IC | **+0.0024** (54.5% pos) | -0.0132 (38.2% pos) | -0.0064 (50.4% pos) |
| | HAC $t$-statistic | +0.12 ($p=0.90$) | -1.27 ($p=0.21$) | -0.35 ($p=0.72$) |
| **Fold 3** (2021-01 to 2021-06) | RMSE | 0.0300 | 0.0300 | 0.0301 |
| (Reflation & Value Rotation) | Mean Daily IC | **+0.0037** (50.4% pos) | -0.0326 (36.1% pos) | -0.0226 (39.5% pos) |
| | HAC $t$-statistic | +0.22 ($p=0.83$) | -1.89 ($p=0.06$) | -1.66 ($p=0.10$) |
| **Fold 4** (2021-07 to 2021-12) | RMSE | 0.0288 | 0.0288 | 0.0288 |
| (Late-Cycle Tech Expansion) | Mean Daily IC | **+0.0414** (58.5% pos) | -0.0125 (40.7% pos) | +0.0198 (56.1% pos) |
| | HAC $t$-statistic | **+1.90** ($p=0.06$) | -1.02 ($p=0.31$) | +1.04 ($p=0.30$) |

### 3.2 Pooled Development Summary (486 Trading Sessions)

| Evaluation Dimension | Market Baseline (Frozen M4) | Financial Specialist (Model 3) | Combined Model (Mkt + Fin) | Incremental Delta ($\Delta = \text{Combined} - \text{Market}$) |
| :--- | :--- | :--- | :--- | :--- |
| **Pooled RMSE** | 0.0589 | **0.0489** | 0.0585 | -0.0004 |
| **Pooled Mean Daily IC** | **+0.0128** | -0.0085 | -0.0027 | **-0.01550** |
| **Median Daily IC** | **+0.0084** | -0.0121 | -0.0075 | -0.01590 |
| **% Positive IC Days** | **51.0%** | 43.4% | 46.1% | -4.9% |
| **HAC $t$-statistic** | +1.04 | -1.23 | -0.23 | **-2.73** |
| **HAC $p$-value** | 0.2969 | 0.2186 | 0.8155 | **0.0065** (Statistically significant degradation) |
| **Gross Annualized Return** | **+6.2%** | -2.1% | +2.7% | -3.5% |
| **Gross Sharpe Ratio** | **+0.92** | -0.39 | +0.43 | -0.49 |

---

## 4. Reused Historical Holdout Evaluation (2022–2023)

Evaluated across **113,549 observations and 490 trading sessions** on the matched cohort:

| Evaluation Dimension | Market Baseline (Frozen M4) | Financial Specialist (Model 3) | Combined Model (Mkt + Fin) | Incremental Delta ($\Delta = \text{Combined} - \text{Market}$) |
| :--- | :--- | :--- | :--- | :--- |
| **Pooled Holdout RMSE** | 0.0306 | 0.0306 | 0.0306 | 0.0000 |
| **Pooled Mean Daily IC** | **+0.0126** | -0.0008 | +0.0083 | **-0.00429** |
| **Median Daily IC** | **+0.0121** | -0.0016 | +0.0076 | -0.00450 |
| **% Positive IC Days** | **52.7%** | 49.4% | 51.0% | -1.7% |
| **HAC Standard Error** | 0.0088 | 0.0055 | 0.0081 | 0.00456 |
| **HAC $t$-statistic** | +1.43 | -0.14 | +1.03 | **-0.94** |
| **HAC $p$-value** | 0.1521 | 0.8893 | 0.3051 | **0.3468** (No significant difference) |
| **2022 Bear Market IC** (246 dates) | **+0.0251** (57.7% pos, $p=0.071$) | -0.0072 (44.3% pos) | +0.0145 (50.4% pos) | -0.0106 ($p=0.18$) |
| **2023 Bull Market IC** (244 dates) | +0.0000 (47.5% pos) | **+0.0057** (54.5% pos) | +0.0021 (51.6% pos) | +0.0021 ($p=0.69$) |

---

## 5. Economic Relevance & Portfolio Simulation

Simulated dollar-neutral strategy: Long top 20% predicted, Short bottom 20% predicted, staggered 5-session holding period (daily turnover ~40%):

| Scenario | Market Baseline (Frozen M4) | Financial Specialist (Model 3) | Combined Model (Mkt + Fin) |
| :--- | :--- | :--- | :--- |
| **Cumulative Gross Return** | **+10.7%** | +6.3% | +6.6% |
| **Gross Annualized Return** | **+5.2%** | +3.1% | +3.3% |
| **Gross Annualized Volatility** | 5.6% | **3.3%** | 4.9% |
| **Gross Sharpe Ratio** | +0.93 | **+0.95** | +0.67 |
| **Maximum Drawdown** | -8.6% | -10.9% | **-8.4%** |
| **Net Return @ 10 bps friction** | **-9.0%** (Sharpe: -0.81) | -12.6% (Sharpe: -2.05) | -12.3% (Sharpe: -1.29) |
| **Net Return @ 20 bps friction** | **-25.2%** (Sharpe: -2.55) | -28.2% (Sharpe: -5.04) | -27.9% (Sharpe: -3.24) |
| **Net Return @ 30 bps friction** | **-38.6%** (Sharpe: -4.28) | -41.0% (Sharpe: -8.04) | -40.8% (Sharpe: -5.19) |

### Key Economic Takeaways:
1. All models collapse into steep negative cumulative returns and negative Sharpe ratios under realistic transaction friction (10 to 30 bps round-trip).
2. The high rebalancing turnover required by a 5-session forecast horizon (~40% daily portfolio turnover) creates a cost barrier of ~10% to 30% per year, completely overwhelming the modest gross alpha spread (+3% to +5% annualized).
3. Financial report signals alone do not improve transaction-cost resilience.

---

## 6. Synthesis: Why Quarterly Financial Data Fails at Short Horizons

The empirical results provide a clear quantitative explanation:
1. **Cadence Mismatch**: SEC financial reports are disclosed quarterly (every 90 days), while the target horizon is 5 trading sessions (1 week).
2. **State Variable vs. Rate-of-Change**: Quarterly accounting ratios (such as ROA, Net Margin, and Debt-to-Equity) are persistent state variables. Over a 5-day trading window, cross-sectional stock returns are driven predominantly by short-term liquidity shocks, technical mean reversion, and macro factor movements, not by changes in quarterly book value.
3. **Information Saturation**: Between 10-Q filing dates, accounting features remain static while prices move daily. A static numerator divided by a dynamic stock price simply turns the fundamental ratio into an inverted proxy for recent price momentum.
4. **Conclusion**: While financial reports are fundamental to multi-month or annual investing horizons, they **do not provide statistically reliable incremental alpha for a 5-session technical prediction model**.

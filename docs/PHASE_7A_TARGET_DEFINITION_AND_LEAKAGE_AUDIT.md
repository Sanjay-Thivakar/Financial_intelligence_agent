# PHASE 7A — TARGET DEFINITION AND LEAKAGE AUDIT REPORT

**Lead Quantitative Researcher & Model Risk Auditor**: AI-Powered Financial Intelligence Agent Architecture Team  
**Evaluation Date**: October 2026  
**Phase**: Phase 7A (Target Re-Engineering & Cross-Sectional Signal Research)  
**Target Code Audited**: [`src/features/target.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/features/target.py), [`scripts/evaluate_phase7a.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/scripts/evaluate_phase7a.py)  
**Machine-Readable Experiment Records**: [`data/processed/research/phase7a/phase7a_experiment_results.json`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/data/processed/research/phase7a/phase7a_experiment_results.json)  

---

## 1. Executive Summary

Phase 7A tested whether reformulating the prediction objective from raw returns to market-neutral and sector-neutral excess returns resolves the target-mismatch defect identified in Phase 6.9E. This audit verified the mathematical formulation, corporate-action adjustment conventions, cohort benchmark construction, inference ranking mechanics, and temporal leakage isolation of all three target specifications across 110,105 observations in the canonical 305-company cohort.

### Core Target Audit Findings:
1. **Target Variance Decomposition Confirmed**:
   - **Target A (Raw Return)**: Total variance = `0.003340` (100.0%).
   - **Target B (Market-Neutral Excess Return)**: Total variance = `0.001964` (**58.8% of raw variance**; market common factor accounts for **41.2%** of raw return variance).
   - **Target C (Sector-Neutral Excess Return)**: Total variance = `0.001530` (**45.8% of raw variance**; market + sector common factors account for **54.2%** of raw return variance).
2. **Absolute Zero-Leakage Guarantee**: Realized market and sector benchmark averages are constructed exclusively on forward return labels ($T+1$ to $T+5$) and are **NEVER** provided to feature matrices. Feature matrices use only information published on or before Session $T$ Market Close (16:00 ET).
3. **5-Session Purge Invariant Strictly Holds**: The 5-session purge gap in trading-session units eliminates target holding window overlap across all 4 walk-forward folds.

---

## 2. Rigorous Formulation of the Three Target Variants

### 2.1 Target A: Original Raw Return (The Control Benchmark)

The established 5-session arithmetic forward return:
$$y_{i, T}^{\text{raw}} = \frac{P_{i, T+5, \text{close}}^{\text{adj}} - P_{i, T+1, \text{open}}^{\text{adj}}}{P_{i, T+1, \text{open}}^{\text{adj}}}$$

- **Decision Timestamp ($T$)**: Session $T$ Market Close (16:00:00 US Eastern Time $\to$ UTC).
- **Execution Timestamp ($T+1$)**: Session $T+1$ Market Open (09:30:00 US Eastern Time $\to$ UTC), executing at $P_{i, T+1, \text{open}}^{\text{adj}}$.
- **Exit Timestamp ($T+5$)**: Session $T+5$ Market Close (16:00:00 US Eastern Time $\to$ UTC), exiting at $P_{i, T+5, \text{close}}^{\text{adj}}$.
- **Corporate Action Adjustments**: Backward adjustment factors incorporate cash dividends, stock dividends, and splits on a total-return basis.
- **Economic Meaning**: Forecasts total unconstrained capital return plus dividend yield. Conflates macroeconomic market beta with firm-specific alpha.

---

### 2.2 Target B: Market-Neutral Excess Return

Defined as the stock's forward return in excess of the contemporaneous equal-weighted cohort benchmark:
$$y_{i, T}^{\text{mkt\_excess}} = y_{i, T}^{\text{raw}} - \bar{y}_{mkt, T}^{\text{raw}}$$
$$\bar{y}_{mkt, T}^{\text{raw}} = \frac{1}{|S_T|} \sum_{j \in S_T} y_{j, T}^{\text{raw}}$$

- **Cohort Benchmark Definition**:
  - Universe $S_T$: The canonical 305 companies from [`data/processed/universe/phase6_9a1_cohort_manifest.csv`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/data/processed/universe/phase6_9a1_cohort_manifest.csv) having valid forward return observations on decision date $T$.
  - Weighting: Equal-weighted across all 305 companies ($|S_T| = 305$ for every session in the 361-session panel).
  - Missingness Handling: Terminal 5 sessions are explicitly masked as `NaN` and dropped from both stock and benchmark computations.
- **Anti-Leakage Safeguard**:
  - The realized benchmark return $\bar{y}_{mkt, T}^{\text{raw}}$ is realized over the future window $[T+1, T+5]$ and is **completely unknown at Session $T$ Market Close**.
  - It is utilized strictly to compute training targets $y_{tr}^{\text{mkt\_excess}}$ and evaluation ground-truth $y_{val}^{\text{mkt\_excess}}$.
  - It is **never fed into model inputs, feature scalers, or imputation pipelines**.
- **Inference Ranking Mechanics**:
  - Because $\bar{y}_{mkt, T}^{\text{raw}}$ is a cross-sectional constant on date $T$, the true cross-sectional rank of raw returns is mathematically identical to the rank of excess returns:
    $$\text{Rank}_i(y_{i, T}^{\text{raw}}) \equiv \text{Rank}_i(y_{i, T}^{\text{mkt\_excess}})$$
  - At live inference time, the model directly outputs predicted relative outperformance $\hat{y}_{i, T}^{\text{mkt\_excess}}$. Sorting stocks in descending order produces a market-neutral long/short ranking signal without needing to forecast the broad market index.

---

### 2.3 Target C: Sector-Neutral Excess Return

Defined as the stock's forward return in excess of its contemporaneous equal-weighted GICS sector benchmark:
$$y_{i, T}^{\text{sec\_excess}} = y_{i, T}^{\text{raw}} - \bar{y}_{\text{sector}(i), T}^{\text{raw}}$$
$$\bar{y}_{s, T}^{\text{raw}} = \frac{1}{|S_{s, T}|} \sum_{j \in S_{s, T}} y_{j, T}^{\text{raw}}$$

- **GICS Sector Allocation**:
  - Sourced from the authoritative cohort manifest established at Phase 6.9A.1:
    Financials (52), Industrials (50), Health Care (49), Consumer Discretionary (40), Consumer Staples (30), Information Technology (25), Energy (17), Communication Services (13), Utilities (12), Materials (9), Real Estate (8).
  - Every company has a 100% valid, fixed GICS sector assignment known point-in-time prior to the sample.
  - Sector group counts range from 8 (Real Estate) to 52 (Financials), satisfying the minimum group size requirements without needing cross-sector pooling.
- **Economic Meaning**: Estimates pure intra-industry idiosyncratic alpha, removing both macro market beta and sector-rotation momentum.

---

## 3. Temporal Isolation & Purge Gap Verification

### 3.1 Mathematical Proof of Zero Boundary Leakage
Let $t \in [0, 360]$ denote trading session calendar indices.

| Fold | Last Train Decision ($t_{\text{tr}}$) | Last Train Target Exit ($t_{\text{tr}} + 5$) | Purge Gap Sessions | First Val Decision ($t_{\text{val}}$) | Separation Margin | Overlap Status |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **0** | Index 172 (`2019-09-09`) | Index 177 (`2019-09-16` Close) | 5 sessions (173–177) | Index 178 (`2019-09-17` Close) | **+1 session** prior to decision | **Zero Overlap** |
| **1** | Index 217 (`2019-11-11`) | Index 222 (`2019-11-18` Close) | 5 sessions (218–222) | Index 223 (`2019-11-19` Close) | **+1 session** prior to decision | **Zero Overlap** |
| **2** | Index 262 (`2020-01-16`) | Index 267 (`2020-01-24` Close) | 5 sessions (263–267) | Index 268 (`2020-01-27` Close) | **+1 session** prior to decision | **Zero Overlap** |
| **3** | Index 307 (`2020-03-23`) | Index 312 (`2020-03-30` Close) | 5 sessions (308–312) | Index 313 (`2020-03-31` Close) | **+1 session** prior to decision | **Zero Overlap** |

In all folds and across all target variants, training holding periods fully settle at $t_{\text{tr}} + 5$ Close, strictly before the validation decision cutoff at $t_{\text{val}}$ Close.

---

## 4. Target Variance Decomposition Analysis

We computed the variance of each target across all 110,105 observations:

$$\text{Var}(y_{\text{raw}}) = \text{Var}(\bar{y}_{mkt}) + \text{Var}(\bar{y}_{sec} - \bar{y}_{mkt}) + \text{Var}(y_{sec\_excess})$$

| Target Level | Target Identifier | Empirical Variance | % of Raw Variance | Variance Removed |
| :--- | :--- | :---: | :---: | :---: |
| **Level 1 (Raw)** | `target_raw` | `0.003340` | 100.0% | 0.0% |
| **Level 2 (Market-Neutral)** | `target_mkt_excess` | `0.001964` | 58.8% | **41.2% (Market Beta Removed)** |
| **Level 3 (Sector-Neutral)** | `target_sec_excess` | `0.001530` | 45.8% | **54.2% (Market + Sector Beta Removed)** |

### Econometric Implication:
Over **54% of raw stock return variance** is explained entirely by common macro and sector shocks. When models are evaluated on raw returns, regression loss functions are dominated by macro market movements, masking stock-specific fundamental valuation signals. Sector-neutral excess returns reduce target noise by more than half, creating a cleaner testbed for cross-sectional stock picking.

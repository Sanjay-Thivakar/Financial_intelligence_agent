# PHASE 7B-D — TARGET DEFINITION AND POINT-IN-TIME LEAKAGE AUDIT

**Phase:** Phase 7B — Historical Data Expansion, Robust Out-of-Sample Validation & Market Signal Acceptance  
**Role:** Senior Quantitative Researcher, Financial ML Engineer & Model-Risk Auditor  
**Date:** October 2026  
**Status:** AUDITED & VERIFIED  

---

## 1. Executive Summary

This audit independently inspects the mathematical definitions, execution timing, benchmark constructions, and information boundaries of all target labels evaluated in Phase 7B.

Three rigorous checks were conducted:
1. **Timing Alignment:** Verified that decision information is available strictly at Session $T$ close (16:00 ET), entry occurs at Session $T+1$ open (09:30 ET), and exit occurs at Session $T+5$ close (16:00 ET).
2. **Benchmark Construction:** Verified that market and sector benchmarks used to compute excess returns are calculated strictly over the forward target interval $[T+1 \text{ open}, T+5 \text{ close}]$ and do not leak future information into decision-time features.
3. **Information Boundary Audit:** Verified that no future prices, future returns, or post-$T$ SEC filings are accessible to the feature engineering pipeline at Session $T$ decision time.

---

## 2. Chronological Timing Invariants

The target engine strictly implements the 5-session forward return contract:

```
Timeline:
Session T (Decision):          Market Close (16:00 ET) -> Feature snapshot frozen (x_{i, T})
[Intervening Night: Non-trading period]
Session T+1 (Executable Entry): Market Open (09:30 ET)  -> Opening auction fill (P_{i, T+1, open}^adj)
Sessions T+2, T+3, T+4:        Holding period
Session T+5 (Executable Exit):  Market Close (16:00 ET) -> Closing auction fill (P_{i, T+5, close}^adj)
```

### Mathematical Formula:
$$y_{i, T}^{\text{raw}} = \frac{P_{i, T+5, \text{close}}^{\text{adj}} - P_{i, T+1, \text{open}}^{\text{adj}}}{P_{i, T+1, \text{open}}^{\text{adj}}}$$

### Pricing Conventions:
- **Corporate Action Adjustments:** All returns use split- and dividend-adjusted prices:
  $$P^{\text{adj}} = P \times \left(\frac{\text{adjusted\_close}}{\text{close}}\right)$$
  ensuring that stock splits, reverse splits, and cash dividends do not introduce artificial return spikes.
- **Terminal Masking:** Observations where $T+5$ exit price is missing (such as the final 5 sessions of 2023 or the terminal 5 sessions of 2020 for the 64 exiting tickers) are explicitly flagged as `target_forward_return_5d_valid = False` and excluded from model training and evaluation.

---

## 3. Benchmark Formulations & Variance Decomposition

### 3.1 Market Benchmark Construction
For each trading date $T$:
$$\bar{y}_{\text{mkt}, T}^{\text{raw}} = \frac{1}{N_T} \sum_{j=1}^{N_T} y_{j, T}^{\text{raw}}$$
- **Constituents:** All active cohort companies with valid target forward returns on date $T$ ($N_T = 305$ in 2019–2020, $N_T = 241$ in 2021–2023).
- **Weighting:** Equal-weighted across all active cohort members.
- **Excess Return:** $y_{i, T}^{\text{mkt}} = y_{i, T}^{\text{raw}} - \bar{y}_{\text{mkt}, T}^{\text{raw}}$.

### 3.2 Sector Benchmark Construction
For each trading date $T$ and each GICS sector $S \in \{1, \dots, 11\}$:
$$\bar{y}_{S, T}^{\text{raw}} = \frac{1}{N_{S, T}} \sum_{j \in S} y_{j, T}^{\text{raw}}$$
- **Constituents:** All active cohort companies belonging to sector $S$ on date $T$.
- **Weighting:** Equal-weighted across constituents in sector $S$.
- **Excess Return:** $y_{i, T}^{\text{sec}} = y_{i, T}^{\text{raw}} - \bar{y}_{\text{sec}(i), T}^{\text{raw}}$.

### 3.3 Verified Target Variance Decomposition (325,578 Valid Observations across 2019–2023)

| Target Formulation | Total Variance | % of Raw Return Variance | Systematic Variance Removed |
| :--- | :--- | :--- | :--- |
| **Target A: Raw Forward Return ($y_i^{\text{raw}}$)** | **0.004112** | **100.0%** | 0.0% (Includes broad market tide) |
| **Target B: Market-Neutral Excess ($y_i^{\text{mkt}}$)** | **0.002526** | **61.4%** | **38.6%** (Market common factor removed) |
| **Target C: Sector-Neutral Excess ($y_i^{\text{sec}}$)** | **0.002047** | **49.8%** | **50.2%** (Market + Sector factors removed) |

#### Critical Finding:
Broad market movements account for **38.6%** of total return variance across the 5-year panel, and sector group movements account for an additional **11.6%**, meaning that **50.2% of raw stock return variance is driven purely by macro and sector tides**.
This mathematically demonstrates why raw-return forecasting models are dominated by market timing noise, whereas cross-sectional stock selection requires market- and sector-neutral targets.

---

## 4. Anti-Leakage Verification Proofs

| Potential Leakage Vector | Audited Mechanism | Verification Result |
| :--- | :--- | :--- |
| **Future Price in Technical Features** | All technical indicators (SMAs, RSI, volatility, momentum) use closing prices up to session $T$ close only. Rolling windows are strictly backward-looking. | **PASSED (No lookahead)** |
| **Future Return in Features** | Target return $y_i$ is calculated from session $T+1$ open to $T+5$ close and exists only as a label column; never present in feature matrices. | **PASSED (No leakage)** |
| **Benchmark Timing Leakage** | Market and sector benchmarks are computed strictly on the forward returns $y_{j, T}$ and subtracted only from target labels; they are never accessible to decision-time features. | **PASSED (No leakage)** |
| **Train/Validation Overlap** | 5-session purge gaps are enforced between every training fold and evaluation fold. | **PASSED (Zero label overlap)** |
| **Preprocessing & Scaler Leakage** | `StandardScaler` and `SimpleImputer` are fitted exclusively on training rows and transformed onto out-of-sample data. | **PASSED (No out-of-sample snooping)** |
| **SEC Filing Availability** | Only filings with `acceptance_timestamp <= session T close (16:00 ET)` are considered in fundamental snapshots. Post-decision restatements are excluded. | **PASSED (Point-in-time safe)** |

---

## 5. Metric Comparability Invariants

1. **RMSE & MAE Invariance Rule:**
   - RMSE of a sector-neutral model (e.g. $\sim 0.045$) cannot be directly compared against RMSE of a raw-return model (e.g. $\sim 0.064$) because the variance of the underlying target is inherently smaller ($0.002047$ vs $0.004112$).
   - A lower RMSE on an excess target **does NOT prove superior predictive skill**—it reflects target variance reduction.
   - All excess return models must be compared **strictly against the Zero-Prediction Baseline ($y=0.0$) evaluated on identical rows and folds**.
2. **Rank Correlation Invariance Rule:**
   - Spearman Rank IC measures cross-sectional ranking accuracy within each daily cross-section and is scale-invariant.
   - Mean daily IC is the primary metric for evaluating pure stock selection ability.

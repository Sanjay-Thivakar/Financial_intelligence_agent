# PHASE 7B-C — FROZEN RESEARCH PROTOCOL AND VALIDATION SPECIFICATION

**Phase:** Phase 7B — Historical Data Expansion, Robust Out-of-Sample Validation & Market Signal Acceptance  
**Protocol Version:** 1.0.0-FROZEN  
**Status:** FROZEN PRIOR TO FINAL HOLDOUT EVALUATION  
**Governing Standard:** Leakage-Free Chronological Walk-Forward Validation, Strict Point-in-Time Correctness & Statistical Hypothesis Testing  

---

## 1. Research Protocol Principles & Quarantined Holdout Rule

To prevent data snooping, p-hacking, and holdout contamination:
1. **Quarantine Rule:** The final evaluation window (January 3, 2022 through December 28, 2023) is strictly quarantined during feature re-engineering, model architecture selection, hyperparameter tuning, and threshold selection.
2. **One-Way Execution:** The final evaluation holdout is inspected **only once**, after all models, hyperparameter grids, and evaluation scripts have been frozen on the development set.
3. **No Retuning:** If results on the final evaluation window are negative, unstable, or statistically nonsignificant, the protocol forbids tweaking hyperparameters, adding features, or filtering tickers to engineer a positive outcome. The true out-of-sample result will be reported honestly.

---

## 2. Universe, Cohort & Exclusions

1. **Universe Definition:**
   - 305 large-cap U.S. equities from the canonical Phase 6.9A.1 cohort across all 11 GICS sectors.
   - For 2019 to mid-2020: 305 companies active.
   - For mid-2020 through 2023: 241 companies with 100% complete, unbroken daily coverage.
2. **Exclusion Criteria:**
   - Observations where $T+5$ exit price is missing (e.g. terminal sessions of the panel) are excluded from evaluation targets.
   - Days where a company has non-positive close prices or missing OHLCV are rejected (none observed).
   - In cross-sectional daily IC calculation, sessions with fewer than 10 valid company returns are excluded (minimum observed is 241).

---

## 3. Target Definitions & Variance Decomposition

All targets are evaluated over an identical 5-session holding horizon:
- **Decision Timestamp ($T$):** Session $T$ Market Close (16:00:00 US Eastern Time).
- **Executable Entry ($T+1$):** Session $T+1$ Market Open (09:30:00 US Eastern Time).
- **Executable Exit ($T+5$):** Session $T+5$ Market Close (16:00:00 US Eastern Time).

### Target Formulations:
1. **Target A: Raw Forward Return ($y_i^{\text{raw}}$)**
   $$y_{i, T}^{\text{raw}} = \frac{P_{i, T+5, \text{close}}^{\text{adj}} - P_{i, T+1, \text{open}}^{\text{adj}}}{P_{i, T+1, \text{open}}^{\text{adj}}}$$

2. **Target B: Market-Neutral Excess Return ($y_i^{\text{mkt}}$)**
   $$y_{i, T}^{\text{mkt}} = y_{i, T}^{\text{raw}} - \bar{y}_{\text{mkt}, T}^{\text{raw}}$$
   where $\bar{y}_{\text{mkt}, T}^{\text{raw}} = \frac{1}{N_T} \sum_{j=1}^{N_T} y_{j, T}^{\text{raw}}$ is the equal-weighted mean return across all active valid cohort companies in session $T$.

3. **Target C: Sector-Neutral Excess Return ($y_i^{\text{sec}}$)**
   $$y_{i, T}^{\text{sec}} = y_{i, T}^{\text{raw}} - \bar{y}_{\text{sec}(i), T}^{\text{raw}}$$
   where $\bar{y}_{\text{sec}(i), T}^{\text{raw}}$ is the equal-weighted mean return across active cohort companies in company $i$'s GICS sector in session $T$.

---

## 4. Feature Space Specifications

### Feature Set 1: Original Market Features (17 Features — Reference Benchmark)
- Returns: `market_return_1d`, `market_return_5d`, `market_return_21d`
- Volatilities: `market_volatility_5d`, `market_volatility_21d`, `market_volatility_63d`
- Momentum: `market_momentum_63d`, `market_momentum_21d` *(collinear duplicate of return_21d)*
- Nominal Dollar SMAs: `market_sma_20d`, `market_sma_50d` *(non-stationary)*
- Distances: `market_distance_sma20`, `market_distance_sma50`
- Normalized & Oscillators: `market_zscore_20d`, `market_zscore_50d`, `market_rsi_14d`
- Volume: `market_volume_change_1d`, `market_volume_ratio_20d`

### Feature Set 2: Cleaned Market Features (15 Features — Cleaned Stationary Candidate)
- Stationary Distance & Ratios:
  - `market_distance_sma20 = (close / market_sma_20d) - 1.0`
  - `market_distance_sma50 = (close / market_sma_50d) - 1.0`
  - `market_sma_ratio = (market_sma_20d / market_sma_50d) - 1.0`
- Dropped: Duplicate momentum (`market_momentum_21d`) and non-stationary dollar SMAs (`market_sma_20d`, `market_sma_50d`).
- Total: 15 stationary, scale-invariant technical indicators.

### Feature Set 3: Cleaned Multimodal Features (22 Features — Development Comparison Only)
- 15 Cleaned Market Features + 7 Validated Fundamental Accounting Features:
  - `fundamental_earnings_yield = (diluted_eps / close).clip(-0.5, 0.5)`
  - `fundamental_net_margin_cl = net_margin.clip(-2.0, 2.0)`
  - `fundamental_roa_cl = roa.clip(-1.0, 1.0)`
  - `fundamental_debt_to_assets_cl = debt_to_assets.clip(0.0, 5.0)`
  - `fundamental_debt_to_equity_cl = debt_to_equity.clip(-5.0, 10.0)`
  - `fundamental_ocf_to_ni_cl = ocf_to_net_income.clip(-10.0, 10.0)`
  - `fundamental_revenue_age_days`

---

## 5. Chronological Split & Validation Architecture

To respect temporal order and prevent label leakage across the 5-session holding horizon:
- **Purge Window:** Exactly 5 trading sessions are purged immediately preceding every evaluation fold. Any training observation whose target return interval $[T+1, T+5]$ overlaps with the validation start session is discarded.
- **Embargo Window:** 0 sessions required post-validation because validation chronologically follows training.
- **Preprocessing Precedence:** SimpleImputer (median) and StandardScaler fit **strictly on the training partition** of each fold and applied to validation/holdout data.

```
Warmup:     [2018-01-02 to 2018-12-31] (251 sessions, warmup for rolling features)

DEVELOPMENT PERIOD (2019-01-02 to 2021-12-31, 757 sessions, 206,283 observations):
Fold 1:     Train [2019-01-02 -> 2019-12-31] (252 sess) | Purge 5 | Val [2020-01-08 -> 2020-06-30] (121 sess)
Fold 2:     Train [2019-01-02 -> 2020-06-30] (377 sess) | Purge 5 | Val [2020-07-09 -> 2020-12-31] (122 sess)
Fold 3:     Train [2019-01-02 -> 2020-12-31] (505 sess) | Purge 5 | Val [2021-01-11 -> 2021-06-30] (119 sess)
Fold 4:     Train [2019-01-02 -> 2021-06-30] (629 sess) | Purge 5 | Val [2021-07-09 -> 2021-12-31] (122 sess)

FINAL HOLDOUT PERIOD (2022-01-03 to 2023-12-28, 500 sessions, 495 valid targets, 119,295 observations):
Final Eval: Train on Full Development [2019-01-02 -> 2021-12-31] (757 sess)
            Purge 5 sessions [2022-01-03 -> 2022-01-07]
            Quarantined Holdout [2022-01-10 -> 2023-12-20] (491 valid sessions, 118,331 observations)
```

---

## 6. Model Specification Matrix

| Model ID | Model Name | Target | Feature Set | Loss / Algorithm | Regularization Tuning |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **B0** | Zero Baseline | Target B / Target C | None ($0.0$) | Trivial constant | None |
| **B_raw** | Train-Mean Baseline | Target A (Raw) | None ($\bar{y}_{\text{train}}$) | Historical mean | None |
| **M1** | Raw Benchmark | Target A (Raw) | Set 1: Orig Market (17) | Ridge (L2) | Inner CV ($\alpha \in [10^{-2}, 10^4]$) |
| **M2** | Cleaned Raw | Target A (Raw) | Set 2: Clean Market (15) | Ridge (L2) | Inner CV ($\alpha \in [10^{-2}, 10^4]$) |
| **M3** | Market-Neutral Clean | Target B (Mkt-Excess) | Set 2: Clean Market (15) | Ridge (L2) | Inner CV ($\alpha \in [10^{-2}, 10^4]$) |
| **M4** | Sector-Neutral Clean | Target C (Sec-Excess) | Set 2: Clean Market (15) | Ridge (L2) | Inner CV ($\alpha \in [10^{-2}, 10^4]$) |
| **M5** | Sector-Neutral Multimodal | Target C (Sec-Excess) | Set 3: Multimodal (22) | Ridge (L2) | Inner CV ($\alpha \in [10^{-2}, 10^4]$) |

---

## 7. Primary & Secondary Evaluation Metrics

### Primary Metric: Daily Cross-Sectional Spearman Rank IC
For each evaluation session $t$:
$$\text{IC}_t = \text{SpearmanCorr}\left(\hat{y}_{i, t}, y_{i, t}\right) \quad \text{across all active cohort companies } i$$
- **Summary Statistics:** Mean Daily IC, Median Daily IC, Standard Deviation, Percentage of Positive IC Days ($\% \text{IC} > 0$).
- **Dependence-Aware Inference:** Newey-West HAC standard error, $t$-statistic, and two-tailed $p$-value with lag $L=4$ (matching the 5-session forward target overlap).

### Secondary Metrics:
- **RMSE & MAE:** Evaluated strictly like-for-like against the zero-prediction baseline on excess return targets.
- **Directional Hit Rate:** Percentage of non-zero predictions matching the sign of actual excess return.
- **Temporal & Sector Stability:** Fold-by-fold IC consistency and mean IC across the 11 GICS sectors.

---

## 8. Economic Simulation Assumptions (Long/Short Quintile Strategy)

To evaluate whether statistical signal translates into economic relevance:
1. **Signal-to-Position Rule:**
   - Top Quintile (Q5: predicted highest 20%): Long position, equal-weighted.
   - Bottom Quintile (Q1: predicted lowest 20%): Short position, equal-weighted.
   - Dollar-neutral (Long 100% / Short 100%, gross leverage 2.0x).
2. **Execution Timing:** Rebalanced daily with 5-session staggered sub-portfolios, entering at $T+1$ open and exiting at $T+5$ close.
3. **Transaction Costs & Slippage Sensitivity:**
   - **Cost Level 1 (Favorable):** 10 bps round-trip (5 bps entry, 5 bps exit).
   - **Cost Level 2 (Realistic Large-Cap):** 20 bps round-trip (10 bps entry, 10 bps exit).
   - **Cost Level 3 (Conservative Friction):** 30 bps round-trip (15 bps entry, 15 bps exit).
4. **Reported Economic Metrics:** Cumulative Return (Gross & Net), Annualized Return, Annualized Volatility, Sharpe Ratio, Maximum Drawdown, Daily Turnover.

---

## 9. Explicit Acceptance & Kill Criteria

| Metric / Requirement | Acceptance Gate | Kill / Limitation Trigger |
| :--- | :--- | :--- |
| **Out-of-Sample Mean Daily IC** | $\text{Mean IC} \ge +0.020$ | $\text{Mean IC} < +0.010$ (negligible ranking ability) |
| **HAC Statistical Significance** | $p_{\text{HAC}} < 0.05$ ($t > 1.96$) | $p_{\text{HAC}} \ge 0.05$ (cannot reject null of zero alpha) |
| **Temporal Stability** | $\% \text{IC} > 0 \ge 53.0\%$ | $\% \text{IC} > 0 < 51.0\%$ (coin flip / unstable) |
| **Final Holdout Generalization** | Positive IC in both 2022 and 2023 | Inverted / negative IC on holdout |
| **Economic Net Sharpe Ratio** | Net Sharpe $> 0.50$ at 20 bps friction | Net Sharpe $\le 0.0$ after realistic costs |

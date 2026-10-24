# PHASE 6.9E — DATA QUALITY AND FEATURE DIAGNOSTICS AUDIT REPORT

**Lead Data Engineer & Quantitative Feature Auditor**: AI-Powered Financial Intelligence Agent Architecture Team  
**Audit Date**: October 2026  
**Phase**: Phase 6.9E (Predictive Signal Diagnosis & Model Improvement)  
**Dataset Audited**: [`data/processed/research/phase6_9d/phase6_9d_multimodal_dataset.parquet`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/data/processed/research/phase6_9d/phase6_9d_multimodal_dataset.parquet) (110,105 rows $\times$ 183 columns, 305 companies, 361 sessions)  
**Machine-Readable Summary**: [`data/processed/research/phase6_9e/phase6_9e_diagnostic_summary.json`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/data/processed/research/phase6_9e/phase6_9e_diagnostic_summary.json)

---

## 1. Executive Summary & Ranked Defect Catalog

A forensic investigation of the 28 multimodal features utilized in Phase 6.9D was conducted. The audit revealed **critical feature engineering defects, structural redundancies, and unit scale mismatches** that explain why previous models failed to learn robust predictive signals:

### Ranked Catalog of Feature Defects & Bottlenecks

| Rank | Defect Description | Affected Features | Root Cause & Mechanism | Impact on Model Training | Severity |
| :---: | :--- | :--- | :--- | :--- | :---: |
| **1** | **Unnormalized Nominal Share Price SMAs** | `market_sma_20d`, `market_sma_50d` | Raw dollar price averages ($3.65 to $2,437.74) pooled across stocks without price normalization. | Cross-sectional standardizer induces massive nominal price bias (e.g. AMZN z-score +10 vs Ford -1); Ridge fits offsetting large coefficients. | **CRITICAL** |
| **2** | **Exact Duplicate Feature Columns** | `market_momentum_5d`, `market_momentum_21d` | Re-computed percentage return identically to `market_return_5d` and `market_return_21d` (diff = 0.0000). | Induces multicollinearity; inflates feature dimensionality with zero incremental information. | **HIGH** |
| **3** | **Zero-Variance Constant Feature** | `fundamental_all_facts_stale` | Value is `False` for 100% of 110,105 rows across all companies and dates. | Variance is 0; standardized feature is identically 0; useless model deadweight. | **HIGH** |
| **4** | **Unnormalized Nominal Per-Share Metric** | `fundamental_diluted_eps` | Raw dollar earnings per share (-$375.88 to +$111.82) pooled across companies without price scaling. | Nominal EPS depends arbitrarily on share count rather than profitability; cannot be compared across companies. | **HIGH** |
| **5** | **Severe Missingness in Debt Ratios** | `fundamental_ratio_debt_to_equity`, `fundamental_ratio_debt_to_assets` | 39.02% and 33.05% missingness across financial firms, utilities, and divergent XBRL balance sheet taxonomies. | Median imputation on training folds replaces over 1/3 of data with synthetic constants, distorting covariance structure. | **MEDIUM** |
| **6** | **Near-Duplicate Return Indicators** | `market_log_return_1d` vs `market_return_1d` | Pairwise correlation $r = 0.9930$; linear model fits large offsetting coefficients ($+0.04$ vs $-0.04$). | Multicollinear coefficient flipping across folds; destabilizes linear weights. | **MEDIUM** |
| **7** | **Zero-Inflated Unsigned Event Counts** | `sec_event_count_5d`, `sec_earnings_release_in_window` | 76.1% of event counts are 0; 91.5% of earnings window flags are 0; zero sentiment/surprise polarity. | High sparsity provides minimal cross-sectional variance; lacks magnitude or sign of earnings surprise. | **MEDIUM** |

---

## 2. Comprehensive 28-Feature Diagnostic Inventory

### 2.1 Market Technical Feature Modality (17 Features)

All market features are computed from split- and dividend-adjusted market price histories available as of Session $T$ Market Close (16:00 ET).

| # | Feature Name | Definition & Transformation | Missing % | Unique | Min | Median | Max | Plausible? | Diagnostic Audit Finding |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **1** | `market_return_1d` | 1-session arithmetic return: $(P_T / P_{T-1}) - 1$ | 0.00% | 109,531 | -0.669 | +0.000 | +1.098 | Yes | Stationary; highly correlated with log return ($r = 0.993$). |
| **2** | `market_return_5d` | 5-session arithmetic return: $(P_T / P_{T-5}) - 1$ | 0.00% | 109,847 | -0.730 | +0.004 | +1.400 | Yes | Stationary; **exact duplicate** of `market_momentum_5d`. |
| **3** | `market_return_21d` | 21-session arithmetic return: $(P_T / P_{T-21}) - 1$ | 0.00% | 110,011 | -0.840 | +0.016 | +1.912 | Yes | Stationary; **exact duplicate** of `market_momentum_21d`. |
| **4** | `market_log_return_1d` | 1-session log return: $\ln(P_T / P_{T-1})$ | 0.00% | 109,531 | -1.106 | +0.000 | +0.741 | Yes | Near-duplicate of arithmetic return ($r = 0.9930$). |
| **5** | `market_volatility_5d` | 5-session rolling annualized return std dev | 0.00% | 110,101 | 0.000 | 0.222 | 8.847 | Yes | Plausible; spiked during March 2020 crash. |
| **6** | `market_volatility_21d`| 21-session rolling annualized return std dev | 0.00% | 110,096 | 0.038 | 0.245 | 4.887 | Yes | Plausible; capture market volatility regime. |
| **7** | `market_volatility_63d`| 63-session rolling annualized return std dev | 0.00% | 110,104 | 0.061 | 0.261 | 3.013 | Yes | Highly persistent volatility regime measure. |
| **8** | `market_momentum_5d` | 5-session momentum | 0.00% | 109,847 | -0.730 | +0.004 | +1.400 | Yes | **EXACT DUPLICATE of `market_return_5d`** (diff = 0.0). |
| **9** | `market_momentum_21d`| 21-session momentum | 0.00% | 110,011 | -0.840 | +0.016 | +1.912 | Yes | **EXACT DUPLICATE of `market_return_21d`** (diff = 0.0). |
| **10**| `market_momentum_63d`| 63-session momentum | 0.00% | 110,072 | -0.875 | +0.046 | +2.383 | Yes | Valid 3-month momentum signal. |
| **11**| `market_sma_20d` | 20-session rolling simple moving average of price | 0.00% | 109,818 | $3.65 | $79.35 | $2,437.74 | **NO** | **DEFECT: Raw nominal dollar price**. Incomparable across stocks. |
| **12**| `market_sma_50d` | 50-session rolling simple moving average of price | 0.00% | 110,032 | $3.86 | $78.84 | $2,382.72 | **NO** | **DEFECT: Raw nominal dollar price**. Collinear with `sma_20d` ($r=0.998$). |
| **13**| `market_zscore_20d` | Normalized price distance from 20-day SMA | 0.00% | 110,105 | -4.471 | +0.283 | +4.472 | Yes | Well-behaved stationary z-score. |
| **14**| `market_zscore_50d` | Normalized price distance from 50-day SMA | 0.00% | 110,104 | -7.000 | +0.334 | +7.000 | Yes | Well-behaved stationary z-score. |
| **15**| `market_rsi_14d` | 14-session Wilder Relative Strength Index [0, 100] | 0.00% | 109,709 | 5.37 | 53.64 | 94.69 | Yes | Bounded technical momentum indicator. |
| **16**| `market_volume_change_1d`| 1-session trading volume ratio $(V_T / V_{T-1}) - 1$ | 0.00% | 109,990 | -0.963 | -0.019 | +38.65 | Yes | Highly skewed right tail; extreme volume spikes. |
| **17**| `market_volume_ratio_20d`| Volume relative to 20-day median volume | 0.00% | 110,100 | 0.026 | 0.967 | 25.10 | Yes | Stationary liquidity indicator. |

---

### 2.2 SEC Fundamental Accounting Feature Modality (8 Features)

Extracted point-in-time from SEC EDGAR XBRL facts with strictly enforced acceptance timestamps $\le$ 16:00 ET decision cutoff.

| # | Feature Name | Accounting Definition | Missing % | Unique | Min | Median | Max | Plausible? | Diagnostic Audit Finding |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **18**| `fundamental_ratio_net_margin` | Net Income / Total Revenue | 4.62% | 2,023 | -28.91 | +0.104 | +12.35 | Yes | Well-behaved profitability ratio; genuine non-coverage for pre-revenue firms. |
| **19**| `fundamental_ratio_roa` | Net Income / Total Assets | 1.31% | 2,094 | -1.72 | +0.038 | +0.865 | Yes | Strongest cross-sectional signal ($r = +0.0296$ with excess target). |
| **20**| `fundamental_ratio_debt_to_assets`| Total Debt / Total Assets | 33.05% | 1,422 | 0.000 | 0.354 | 4.887 | Partially | **High missingness (33%)**; banks/financials report divergent liabilities concepts. |
| **21**| `fundamental_ratio_debt_to_equity`| Total Debt / Stockholders Equity | 39.02% | 1,294 | -110.5 | 0.892 | 872.2 | Partially | **High missingness (39%)**; negative equity in distressed/leveraged buyback firms creates wild ratios. |
| **22**| `fundamental_ratio_ocf_to_net_income`| Operating Cash Flow / Net Income | 10.29% | 1,886 | -89.4 | 1.306 | 134.1 | Yes | Accruals quality proxy; extreme ratios when Net Income $\approx 0$. |
| **23**| `fundamental_diluted_eps` | Diluted Earnings Per Share | 1.79% | 899 | -$375.88 | $2.59 | $111.82 | **NO** | **DEFECT: Unscaled nominal per-share dollar figure**. GOOG $30 vs BAC $1.73. |
| **24**| `fundamental_revenue_age_days` | Elapsed calendar days since latest revenue fact filing | 3.30% | 257 | 1.0 | 56.0 | 258.0 | Yes | Staggered quarterly reporting cadence proxy. |
| **25**| `fundamental_all_facts_stale` | Binary flag: True if facts $> 180$ days old | **0.00%** | **1** | **False** | **False** | **False** | **NO** | **DEFECT: Constant feature (Zero Variance)**. Useless deadweight. |

---

### 2.3 SEC Corporate Event Feature Modality (3 Features)

Extracted from SEC Form 8-K filings with a mandatory 5-minute dissemination buffer ($T_{\text{acceptance}} + 5\text{m} \le T_{\text{close}}$).

| # | Feature Name | Event Definition | Missing % | Unique | Distribution Characteristics | Plausible? | Diagnostic Audit Finding |
| :---: | :--- | :--- | :---: | :---: | :---: | :--- | :---: | :--- |
| **26**| `sec_event_count_5d` | Count of Form 8-K filings in rolling 5-session window | 0.00% | 8 | 0 (76.1%), 1 (19.6%), 2 (3.5%), $\ge 3$ (0.8%) | Yes | Zero-inflated count; no information for 76% of instances. |
| **27**| `sec_earnings_release_in_window` | Binary flag: Item 2.02 earnings release in 5-day window | 0.00% | 2 | 0 (91.5%), 1 (8.5%) | Yes | Highly sparse; lacks earnings surprise magnitude or sign. |
| **28**| `sec_days_since_last_8k` | Elapsed calendar days since latest Form 8-K | 11.98% | 93,434 | Min 0.0, Median 17.3, Max 179.2 days | Yes | Missingness corresponds to companies with zero prior 8-Ks in sample. |

---

## 3. Forensic Analysis of Feature Bottlenecks

### 3.1 The Nominal Price Moving Average Defect (`market_sma_20d`, `market_sma_50d`)
- In [`src/models/baseline.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/models/baseline.py), `market_sma_20d` and `market_sma_50d` were included in the baseline feature vector.
- Inspection of the actual data values demonstrates that these are **unnormalized dollar moving averages**:
  - Ford Motor (`F`): SMA $20 \approx \$7.73$
  - Apple (`AAPL`): SMA $20 \approx \$161.14$
  - Amazon (`AMZN`): SMA $20 \approx \$1,558.43$
  - Google (`GOOG`): SMA $20 \approx \$1,037.84$
- **Econometric Consequence**:
  1. Share price levels in equity markets are completely arbitrary artifacts of historical split decisions and share counts. A stock at $10 with 1 billion shares has the identical capitalization as a stock at $1,000 with 10 million shares.
  2. When standardizing pooled data across 305 companies using `StandardScaler()`, `market_sma_20d` creates huge artificial cross-sectional biases (AMZN gets a z-score of $+10$, Ford gets $-1.5$).
  3. Furthermore, because `market_sma_20d` and `market_sma_50d` have a pairwise correlation of **$r = 0.9980$**, linear Ridge fits offsetting large coefficients (e.g. $-0.0199$ on SMA 20 and $+0.0203$ on SMA 50), acting as an accidental differencing term while destabilizing the linear system.
- **Prescribed Remediation**:
  Replace raw dollar price SMAs with **dimensionless stationary price ratios**:
  $$\text{dist\_sma20} = \frac{P_t}{\text{SMA}_{20,t}} - 1$$
  $$\text{dist\_sma50} = \frac{P_t}{\text{SMA}_{50,t}} - 1$$
  $$\text{sma\_ratio} = \frac{\text{SMA}_{20,t}}{\text{SMA}_{50,t}} - 1$$

### 3.2 Exact Duplicate Features (`market_momentum_5d`, `market_momentum_21d`)
- In [`src/features/market.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/features/market.py), `market_momentum_5d` was computed using the identical formula as `market_return_5d`:
  $$\max | \text{market\_return\_5d} - \text{market\_momentum\_5d} | = 0.00000000$$
  $$\max | \text{market\_return\_21d} - \text{market\_momentum\_21d} | = 0.00000000$$
- This duplicated two columns identically, adding multicollinear redundancy to the linear models.

### 3.3 Zero-Variance Constant Feature (`fundamental_all_facts_stale`)
- In [`src/features/fundamental.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/features/fundamental.py), `fundamental_all_facts_stale` was defined to flag whether all facts are $>180$ days old.
- Across all 110,105 observations in the 305-company dataset, this column is **False for every single row**.
- Its empirical variance is identically 0.0, providing zero predictive signal.

### 3.4 Unscaled Nominal Per-Share Metric (`fundamental_diluted_eps`)
- Diluted EPS was included as raw nominal dollars.
- A high EPS does not indicate a cheap or profitable stock (a $1,000 stock with $10 EPS has a P/E of 100, while a $20 stock with $2 EPS has a P/E of 10).
- Across the cross-section, nominal EPS ranges from -$375.88 to +$111.82, injecting arbitrary per-share scaling noise into the regression.

---

## 4. Prescribed Cleaned Feature Specification

To remediate these defects without breaking pipeline contracts, we constructed a **Cleaned 24-Feature Stationary Specification**:
1. **Drop Exact Duplicates**: Remove `market_momentum_5d` and `market_momentum_21d`.
2. **Drop Near-Duplicate**: Remove `market_log_return_1d` ($r=0.993$ with arithmetic return).
3. **Drop Constant**: Remove `fundamental_all_facts_stale` (variance = 0).
4. **Drop Unnormalized Nominal Dollar Quantities**: Remove raw `market_sma_20d`, `market_sma_50d`, and `fundamental_diluted_eps`.
5. **Add Stationary Normalized Moving Average Ratios**:
   - `market_distance_sma20` = $(P_t / \text{SMA}_{20,t}) - 1$
   - `market_distance_sma50` = $(P_t / \text{SMA}_{50,t}) - 1$
   - `market_sma_ratio` = $(\text{SMA}_{20,t} / \text{SMA}_{50,t}) - 1$

This cleaned feature set preserves 100% of the economic information while removing non-stationary price artifacts and redundant columns.

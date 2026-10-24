# PHASE 6.9D — MULTIMODAL DATASET SCHEMA AND FEATURE DICTIONARY

**Dataset Identifier**: `phase6_9d_multimodal_dataset.parquet`  
**Location**: `data/processed/research/phase6_9d/phase6_9d_multimodal_dataset.parquet`  
**Creation Date**: October 2026  
**Total Observations**: 110,105 rows  
**Total Columns**: 183 columns (32 core modeling columns + provenance metadata)  
**Authoritative Cohort**: 305 companies (S&P 500 survivorship-controlled cohort)  
**Historical Evaluation Window**: January 2, 2019 through June 8, 2020 (361 trading sessions per company)  
**Storage Invariant**: Free, zero-budget, point-in-time compliant  

---

## 1. Dataset Architecture & Observation Contract

| Specification | Project Convention & Formal Definition |
| :--- | :--- |
| **Observation Key** | Composite primary key `(company_id, trading_date)` represented uniquely as `dataset_row_id` (`company_id|YYYY-MM-DDTHH:MM:SSZ`). |
| **Row Uniformity** | Exactly 361 rows per company across all 305 cohort members ($305 \times 361 = 110,105$ observations). Zero missing sessions. |
| **Decision Cutoff** | Session $T$ Market Close (16:00:00 US Eastern Time -> UTC). Daylight-saving aware (EDT UTC-4 / EST UTC-5). |
| **Execution Cutoff** | Session $T+1$ Market Open (09:30:00 US Eastern Time -> UTC). |
| **Trade Exit Cutoff** | Session $T+5$ Market Close (16:00:00 US Eastern Time -> UTC). |
| **Information Bound** | All feature inputs must be known strictly on or before Session $T$ Close. Filings accepted after $T$ close are strictly excluded. |

---

## 2. Core Feature Dictionary

### 2.1 Target Variable (Forward Return)

| Column Name | Mathematical Formula | Unit | Information Cutoff | Missing-Data Policy | Known Limitations |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `target_forward_return_5d` | $y_T^{(5)} = \frac{P_{T+5, \text{close}}^{\text{adj}} - P_{T+1, \text{open}}^{\text{adj}}}{P_{T+1, \text{open}}^{\text{adj}}}$ | Ratio | $T+5$ Market Close | Masked as NaN for terminal sessions where $T+5$ close is unavailable. | Overlapping 5-session holding horizon causes serial autocorrelation in targets; requires Newey-West HAC inference. |
| `target_forward_return_5d_valid` | Boolean validity flag | Bool | $T+5$ Market Close | False if terminal rows lack future pricing. | Only rows with `True` enter model training and out-of-sample evaluation. |

---

### 2.2 Market Features (17 Technical & Price-Action Metrics)

All market features are derived strictly from historical daily pricing up to Session $T$ Close:

| Feature Column | Formula / Definition | Unit | Cutoff Rule | Missing-Data Policy |
| :--- | :--- | :---: | :--- | :--- |
| `market_return_1d` | $(P_T^{\text{adj}} - P_{T-1}^{\text{adj}}) / P_{T-1}^{\text{adj}}$ | Ratio | $T$ close | 0.0% missing (warmed from 2018-01-01) |
| `market_return_5d` | $(P_T^{\text{adj}} - P_{T-5}^{\text{adj}}) / P_{T-5}^{\text{adj}}$ | Ratio | $T$ close | 0.0% missing |
| `market_return_21d` | $(P_T^{\text{adj}} - P_{T-21}^{\text{adj}}) / P_{T-21}^{\text{adj}}$ | Ratio | $T$ close | 0.0% missing |
| `market_log_return_1d` | $\ln(P_T^{\text{adj}} / P_{T-1}^{\text{adj}})$ | Log ratio | $T$ close | 0.0% missing |
| `market_volatility_5d` | $\sigma_{5d} \times \sqrt{252}$ (rolling std of log returns) | Ann. Vol | $T$ close | 0.0% missing |
| `market_volatility_21d` | $\sigma_{21d} \times \sqrt{252}$ | Ann. Vol | $T$ close | 0.0% missing |
| `market_volatility_63d` | $\sigma_{63d} \times \sqrt{252}$ | Ann. Vol | $T$ close | 0.0% missing |
| `market_momentum_5d` | $(P_T^{\text{adj}} / P_{T-5}^{\text{adj}}) - 1.0$ | Ratio | $T$ close | 0.0% missing |
| `market_momentum_21d` | $(P_T^{\text{adj}} / P_{T-21}^{\text{adj}}) - 1.0$ | Ratio | $T$ close | 0.0% missing |
| `market_momentum_63d` | $(P_T^{\text{adj}} / P_{T-63}^{\text{adj}}) - 1.0$ | Ratio | $T$ close | 0.0% missing |
| `market_sma_20d` | $\frac{1}{20}\sum_{i=0}^{19} P_{T-i}^{\text{adj}}$ | USD ($) | $T$ close | 0.0% missing |
| `market_sma_50d` | $\frac{1}{50}\sum_{i=0}^{49} P_{T-i}^{\text{adj}}$ | USD ($) | $T$ close | 0.0% missing |
| `market_zscore_20d` | $(P_T^{\text{adj}} - \text{SMA}_{20}) / \sigma_{20}$ | Std Devs | $T$ close | 0.0% missing |
| `market_zscore_50d` | $(P_T^{\text{adj}} - \text{SMA}_{50}) / \sigma_{50}$ | Std Devs | $T$ close | 0.0% missing |
| `market_rsi_14d` | $100 - (100 / (1 + \text{RS}_{14}))$, Wilder smoothed | Index [0, 100] | $T$ close | 0.0% missing |
| `market_volume_change_1d` | $(V_T - V_{T-1}) / V_{T-1}$ | Ratio | $T$ close | 0.0% missing |
| `market_volume_ratio_20d` | $V_T / \text{SMA}(V, 20)$ | Ratio | $T$ close | 0.0% missing |

---

### 2.3 Fundamental Features (8 Accounting Health & Valuation Ratios)

Derived from `phase6_9c_financial_facts_consolidated_v2.parquet` under strict point-in-time isolation:

| Feature Column | Formula / Accounting Concepts | Unit | Missingness Rate | Missing-Data / Imputation Policy |
| :--- | :--- | :---: | :---: | :--- |
| `fundamental_ratio_net_margin` | $\text{NetIncome} / \text{Revenue}$ | Ratio | 4.62% | Preserved as NaN in derived dataset; imputed strictly via training fold median. |
| `fundamental_ratio_roa` | $\text{NetIncome} / \text{TotalAssets}$ | Ratio | 1.31% | Preserved as NaN; training fold median imputation. |
| `fundamental_ratio_debt_to_assets` | $\text{TotalLiabilities} / \text{TotalAssets}$ | Ratio | 33.05% | Financial institutions and certain REITs omit standard liabilities; preserved as NaN. |
| `fundamental_ratio_debt_to_equity` | $\text{TotalLiabilities} / \text{StockholdersEquity}$ | Ratio | 39.02% | Preserved as NaN when negative equity or unclassified debt exists. |
| `fundamental_ratio_ocf_to_net_income` | $\text{OperatingCashFlow} / \text{NetIncome}$ | Ratio | 10.29% | NaN when NetIncome $\le 0$ or cash flow omitted. |
| `fundamental_diluted_eps` | Diluted Earnings Per Share GAAP Fact | USD / Share | 1.79% | Direct point-in-time GAAP XBRL fact. |
| `fundamental_revenue_age_days` | $(T_{\text{decision}} - T_{\text{acceptance}}) / 86400.0$ | Days | 3.30% | Number of days elapsed since latest revenue report. |
| `fundamental_all_facts_stale` | Binary flag ($1$ if all facts $>400$ days old, else $0$) | Binary (0/1) | 0.00% | Explicit boolean indicator. |

---

### 2.4 Corporate Event Features (3 SEC Form 8-K Indicators)

Derived from `phase6_9c_8k_events_consolidated_v2.parquet` with 5-minute dissemination buffer ($T_{\text{acceptance}} + 5\text{m} \le T_{\text{decision}}$):

| Feature Column | Definition | Unit | Missingness Rate | Missing-Data / Imputation Policy |
| :--- | :--- | :---: | :---: | :--- |
| `sec_event_count_5d` | Number of verified Form 8-Ks published in trailing 5 trading sessions ending on session $T$. | Integer Count | 0.00% | 0 if verified active company had no filing; never converted from missing source. |
| `sec_earnings_release_in_window` | Binary indicator ($1$ if Item 2.02 Results of Operations was filed in 5-day window, else $0$). | Binary (0/1) | 0.00% | 0 if no Item 2.02 occurred in window. |
| `sec_days_since_last_8k` | Calendar days elapsed since most recent eligible Form 8-K as of session $T$ close. | Days | 11.98% | NaN if company had zero historical 8-Ks prior to date; imputed with training fold median. |

---

## 3. Metadata and Tracking Columns

| Column | Type | Description |
| :--- | :---: | :--- |
| `dataset_row_id` | String | Unique row identifier (`company_id|decision_timestamp`). |
| `company_id` | String | Canonical cohort identifier (`US_CIK_000XXXXXXX`). |
| `ticker` | String | Primary trading ticker symbol. |
| `trading_date` | String | Market trading session date (`YYYY-MM-DD`). |
| `sector` | String | GICS economic sector classification (11 unique sectors). |
| `decision_timestamp` | Timestamp (UTC) | Exact cutoff timestamp for Session $T$ Close (16:00 ET). |
| `execution_timestamp` | Timestamp (UTC) | Exact cutoff timestamp for Session $T+1$ Open (09:30 ET). |
| `is_complete_case` | Boolean | True if all 28 candidate features are populated without NaNs. |
| `fundamental_available` | Boolean | True if company facts were active as of decision cutoff. |
| `sec_event_available` | Boolean | True if SEC Form 8-K coverage was active for entity. |
| `dataset_builder_provenance` | String | Exact builder script version (`phase6_9d_point_in_time_builder_v1`). |

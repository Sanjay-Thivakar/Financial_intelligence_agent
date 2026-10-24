# PHASE 8 — FINANCIAL FEATURE ENGINEERING REPORT

**Phase:** Phase 8 — Financial Reports Intelligence Model  
**Role:** Senior Quantitative Researcher & Financial ML Engineer  
**Date:** October 2026  
**Status:** COMPLETE & INDEPENDENTLY AUDITED  

---

## 1. Executive Summary & Design Philosophy

The objective of Phase 8 feature engineering is to synthesize an auditable, economically interpretable set of financial report features from normalized SEC EDGAR XBRL facts.

Rather than blindly calculating hundreds of unvetted ratios, Phase 8 constructs **15 focused, theoretically grounded fundamental features** spanning five core corporate dimensions:
1. **Profitability & Margins**: How efficiently the firm converts revenues into gross profit, operating income, and net earnings.
2. **Capital Structure & Solvency**: The degree of balance sheet leverage and ability to service commitments.
3. **Liquidity & Working Capital**: Short-term cash and buffer assets relative to liabilities.
4. **Cash Flow & Earnings Quality**: Cash conversion efficiency and non-cash accounting accruals.
5. **Point-in-Time Valuation**: Price-relative earnings yield computed using unrevised closing prices at signal time.

Every feature enforces:
- Explicit XBRL tag mappings across US-GAAP taxonomies.
- Safe division guards (rejects divide-by-zero or negative denominator anomalies).
- Realistic accounting bounds and winsorization to prevent outlier distortion.
- Point-in-time public acceptance timestamps.
- Explicit missingness tracking (never treats missing facts as zero).

---

## 2. Feature Dictionary & Specifications

### 2.1 Profitability Family
| Feature Column | Accounting Formula | Primary US-GAAP Concept Tags | Economic Bounds | Missingness (327k rows) |
| :--- | :--- | :--- | :--- | :--- |
| `fin_gross_margin` | $\frac{\text{Gross Profit}}{\text{Revenues}}$ | `GrossProfit`, `Revenues`, `CostOfRevenue` | `[-1.0, 1.0]` | 32.23% (Banks/Fin lack Gross Profit) |
| `fin_operating_margin` | $\frac{\text{Operating Income}}{\text{Revenues}}$ | `OperatingIncomeLoss`, `Revenues` | `[-1.0, 1.0]` | 22.91% |
| `fin_net_margin` | $\frac{\text{Net Income}}{\text{Revenues}}$ | `NetIncomeLoss`, `ProfitLoss`, `Revenues` | `[-2.0, 2.0]` | 3.56% |
| `fin_roa` | $\frac{\text{Net Income}}{\text{Total Assets}}$ | `NetIncomeLoss`, `Assets` | `[-1.0, 1.0]` | 0.62% |
| `fin_roe` | $\frac{\text{Net Income}}{\text{Stockholders' Equity}}$ | `NetIncomeLoss`, `StockholdersEquity` | `[-2.0, 2.0]` | 9.43% |

### 2.2 Financial Health & Liquidity Family
| Feature Column | Accounting Formula | Primary US-GAAP Concept Tags | Economic Bounds | Missingness (327k rows) |
| :--- | :--- | :--- | :--- | :--- |
| `fin_debt_to_assets` | $\frac{\text{Total Liabilities}}{\text{Total Assets}}$ | `Liabilities`, `Assets`, `StockholdersEquity` | `[0.0, 5.0]` | 1.47% |
| `fin_debt_to_equity` | $\frac{\text{Total Liabilities}}{\text{Stockholders' Equity}}$ | `Liabilities`, `StockholdersEquity` | `[-5.0, 10.0]` | 8.85% |
| `fin_current_ratio` | $\frac{\text{Current Assets}}{\text{Current Liabilities}}$ | `AssetsCurrent`, `LiabilitiesCurrent` | `[0.0, 10.0]` | 16.02% (Financials lack current/non-current) |
| `fin_cash_to_assets` | $\frac{\text{Cash \& Equivalents}}{\text{Total Assets}}$ | `CashAndCashEquivalentsAtCarryingValue`, `Assets` | `[0.0, 1.0]` | 5.37% |

### 2.3 Cash Flow & Earnings Quality Family
| Feature Column | Accounting Formula | Primary US-GAAP Concept Tags | Economic Bounds | Missingness (327k rows) |
| :--- | :--- | :--- | :--- | :--- |
| `fin_ocf_to_assets` | $\frac{\text{Operating Cash Flow}}{\text{Total Assets}}$ | `NetCashProvidedByUsedInOperatingActivities`, `Assets` | `[-1.0, 1.0]` | 2.25% |
| `fin_fcf_to_assets` | $\frac{\text{Operating Cash Flow} - \text{CapEx}}{\text{Total Assets}}$ | `NetCashProvidedByUsedInOperatingActivities`, `PaymentsToAcquirePropertyPlantAndEquipment` | `[-1.0, 1.0]` | 10.53% |
| `fin_ocf_to_net_income` | $\frac{\text{Operating Cash Flow}}{\text{Net Income}}$ | `NetCashProvidedByUsedInOperatingActivities`, `NetIncomeLoss` | `[-10.0, 10.0]` | 2.83% |
| `fin_accruals` | $\frac{\text{Net Income} - \text{Operating Cash Flow}}{\text{Total Assets}}$ | `NetIncomeLoss`, `NetCashProvidedByUsedInOperatingActivities`, `Assets` | `[-2.0, 2.0]` | 2.83% |

### 2.4 Valuation & Disclosure Family
| Feature Column | Accounting Formula | Input Sources | Economic Bounds | Missingness (327k rows) |
| :--- | :--- | :--- | :--- | :--- |
| `fin_earnings_yield` | $\frac{\text{Diluted EPS}}{\text{Closing Price}}$ | `EarningsPerShareDiluted`, `market.close` | `[-0.5, 0.5]` | 1.05% |
| `fin_filing_age_days` | $\frac{T_{\text{close\_utc}} - T_{\text{acceptance}}}{86400}$ | `acceptance_timestamp`, `session_date` | `[0, \infty)` | 0.04% |
| `fin_is_stale_180` | `filing_age_days > 180` | Staleness flag | `{0, 1}` | 0.00% |
| `fin_is_amended` | `form in ("10-K/A", "10-Q/A")` | Filing form type | `{0, 1}` | 0.00% |

---

## 3. Sector Missingness & Structural Taxonomy Heterogeneity

Financial accounting standards differ structurally by sector under US-GAAP:
1. **Financials & Insurance (52 companies, 17.0% of cohort)**:
   - Financial institutions do not report classified balance sheets (no `AssetsCurrent` or `LiabilitiesCurrent`). Consequently, `fin_current_ratio` is legitimately absent for banks.
   - Financial institutions do not report `GrossProfit` or `CostOfGoodsAndServicesSold` (interest income vs non-interest expense). Consequently, `fin_gross_margin` is legitimately absent.
2. **Utilities & Capital-Intensive Sectors**:
   - Heavy depreciation schedules cause operating cash flows to diverge significantly from net income, making `fin_accruals` and `fin_ocf_to_assets` highly informative.
3. **Core Financial Flag (`fin_core_valid`)**:
   - Defined as: `fin_fresh_180 & fin_net_margin.notna() & fin_roa.notna() & fin_debt_to_assets.notna()`.
   - Across the 327,103 rows, **94.6% of observations (309,321 rows)** satisfy `fin_core_valid == True`.
   - Yearly completeness:
     - 2019: 93.8%
     - 2020: 94.5%
     - 2021: 94.9%
     - 2022: 95.7%
     - 2023: 96.7%

---

## 4. Preprocessing & Outlier Treatment Protocol

To prevent look-ahead bias and distribution contamination:
1. **No Target-Aware Scaling**: Standard scaling parameters $(\mu, \sigma)$ are fitted strictly on each training fold:
   $$z = \frac{x - \mu_{\text{train}}}{\sigma_{\text{train}}}$$
2. **Median Imputation**: Missing values are imputed using the **training fold median**:
   $$x_{\text{imp}} = \text{median}(x_{\text{train}})$$
   Validation and holdout observations never contribute to the imputed median.
3. **Stationarity**: All features are expressed as dimensionless ratios, percentages, yields, or days of age. No raw dollar amounts (such as nominal revenue or raw book value) enter the feature matrix.

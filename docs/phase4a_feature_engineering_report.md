# Phase 4A Final Report: Point-in-Time Feature Engineering Foundation (Post-Audit Edition)

## Executive Summary

Phase 4A delivers a tested, modular, and mathematically rigorous feature-engineering foundation for our US equities financial intelligence agent. The foundation extracts technical market features, harmonizes point-in-time SEC EDGAR fundamental statements and financial health ratios, aligns them strictly at exchange-aware trading-session decision cutoffs, and enforces conservative data-storage governance.

Following a pre-acceptance audit, targeted corrections resolved three critical defects:
1. **Exchange-Local Decision Timestamps & DST Resolution**:
   - Replaced hard-coded UTC offsets with [`MarketCalendar`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/features/calendar.py), converting NYSE/NASDAQ hours via IANA `America/New_York`.
   - Correctly distinguishes Eastern Daylight Time (EDT, UTC-4: market close at **20:00:00 UTC**) from Eastern Standard Time (EST, UTC-5: market close at **21:00:00 UTC**), early closes (13:00 ET = 17:00 or 18:00 UTC), and next-session opens (09:30 ET = 13:30 or 14:30 UTC), skipping weekends and official exchange holidays.
   - Confirmed look-ahead leakage fix: SEC filings released after market close (e.g. 16:15 ET / 20:15 UTC on 2023-05-26) are strictly excluded from same-day market close decisions.
2. **Fundamental Concept Alias Priority Across Periods**:
   - Hardened [`FundamentalFeatureEngine._extract_latest_concept_fact`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/features/fundamental.py#L126-L163) to evaluate all concept aliases collectively, finding the global maximum `period_end` rather than stopping on an obsolete historical tag (e.g. correctly capturing 2023 revenue under `RevenueFromContractWithCustomer...` rather than stopping at 2017 `Revenues`).
3. **Market Feature Hardening**:
   - Deduplicates trading sessions per company, guards against non-positive price anomalies, and guards volume change against zero or negative prior volume.
4. **Conservative Storage Policy**:
   - Refrains from claiming derived works are legally exempt; explicitly treats legal authorization as **UNVERIFIED** without written commercial agreements.
5. **Test Suite Health**:
   - Full test suite expanded to **56 of 56 tests passing** in 2.74s with 0 warnings.

---

## 1. Mathematical Formulas & Feature Definitions

### 1.1 Market Technical Features

Let $P_t^{adj}$ denote the dividend-and-split adjusted closing price, $P_t$ the unadjusted closing price, and $V_t$ the trading volume on trading day $t$:

| Feature | Mathematical Definition | Lookback Windows | Purpose |
| :--- | :--- | :---: | :--- |
| **Simple Daily Return** | $r_t = \frac{P_t^{adj} - P_{t-1}^{adj}}{P_{t-1}^{adj}}$ | $1, 5, 21$ days | Baseline period-over-period economic price change. |
| **Log Daily Return** | $r_t^{log} = \ln\left(\frac{P_t^{adj}}{P_{t-1}^{adj}}\right)$ | $1$ day | Additive, time-consistent return metric for volatility modeling. |
| **Momentum** | $\text{Mom}_{k, t} = \frac{P_t^{adj} - P_{t-k}^{adj}}{P_{t-k}^{adj}}$ | $k \in \{5, 21, 63, 126\}$ | Multi-scale intermediate and long-term trend following. |
| **Rolling Volatility** | $\sigma_{w, t} = \sqrt{\frac{1}{w-1}\sum_{i=0}^{w-1}(r_{t-i}^{log} - \bar{r}_t^{log})^2} \times \sqrt{252}$ | $w \in \{5, 21, 63\}$ | Annualized sample standard deviation of daily log returns. |
| **Rolling Price Mean & Z-Score** | $\mu_{w, t} = \frac{1}{w}\sum_{i=0}^{w-1}P_{t-i}^{adj}$<br>$z_{w, t} = \frac{P_t^{adj} - \mu_{w, t}}{\sigma_{P, w, t}}$ | $w \in \{20, 50, 200\}$ | Moving average baseline and normalized distance from trend. |
| **Relative Strength Index (RSI)** | $\Delta P_t = P_t^{adj} - P_{t-1}^{adj}$<br>$U_t = \max(\Delta P_t, 0), D_t = \max(-\Delta P_t, 0)$<br>$\bar{U}_t = \text{EMA}_{14}(U), \bar{D}_t = \text{EMA}_{14}(D)$<br>$\text{RSI} = 100 - \frac{100}{1 + \bar{U}_t / \bar{D}_t}$ | $14$ days | Overbought ($>70$) vs oversold ($<30$) mean-reversion indicator. |
| **Volume Ratio** | $\bar{V}_{20, t} = \frac{1}{20}\sum_{i=0}^{19}V_{t-i}$<br>$\text{VR}_{20, t} = \frac{V_t}{\bar{V}_{20, t}}$ | $20$ days | Relative liquidity surge indicator. |

### 1.2 Fundamental Accounting Features & Ratios

Features are extracted from SEC EDGAR XBRL facts as of cutoff $T_{\text{decision}}$, where $\text{acceptance\_timestamp} \le T_{\text{decision}}$:

| Concept / Metric | Formula / Source GAAP Concept | Missing Handling | Economic Significance |
| :--- | :--- | :--- | :--- |
| **Revenue** | `Revenues` $\lor$ `RevenueFromContractWithCustomer...` $\lor$ `SalesRevenueNet` | Preserved as `NaN` | Top-line quarterly/annual business scale. |
| **Net Income** | `NetIncomeLoss` $\lor$ `ProfitLoss` | Preserved as `NaN` | Bottom-line earnings available to equity holders. |
| **Total Assets** | `Assets` | Preserved as `NaN` | Aggregate economic resource base. |
| **Total Liabilities** | `Liabilities` | Preserved as `NaN` | Aggregate financial and contractual obligations. |
| **Operating Cash Flow** | `NetCashProvidedByUsedInOperatingActivities` | Preserved as `NaN` | Actual cash generation from core operations. |
| **Debt-to-Assets** | $\frac{\text{Total Liabilities}}{\text{Total Assets}}$ | `NaN` if Assets $\le 0$ or either missing | Total financial leverage and solvency cushion. |
| **Debt-to-Equity** | $\frac{\text{Total Liabilities}}{\text{Stockholders' Equity}}$ | `NaN` if Equity $\le 0$ or either missing | Financial risk relative to book net worth. |
| **Net Profit Margin** | $\frac{\text{Net Income}}{\text{Revenue}}$ | `NaN` if Revenue $\le 0$ or either missing | Operating conversion efficiency. |
| **Return on Assets (ROA)** | $\frac{\text{Net Income}}{\text{Total Assets}}$ | `NaN` if Assets $\le 0$ or either missing | Asset productivity and capital efficiency. |
| **Current Ratio** | $\frac{\text{Current Assets}}{\text{Current Liabilities}}$ | `NaN` if Curr. Liab $\le 0$ or missing | Short-term liquidity cushion. |
| **OCF-to-Net-Income** | $\frac{\text{Operating Cash Flow}}{\text{Net Income}}$ | `NaN` if Net Income $= 0$ or missing | Earnings quality and cash conversion ratio. |

---

## 2. Integrity Safeguards & Pre-Acceptance Corrections

### 2.1 Exchange-Local Decision Timestamps & Timezone Architecture
* **Identified Defect**: The initial implementation hardcoded `+ 21:00:00 UTC` for market close and `+ 13:30:00 UTC` for next open.
  - On 2023-05-26 (Eastern Daylight Time, UTC-4), US exchanges closed at 16:00 ET = **20:00:00 UTC**. A decision cutoff at 21:00:00 UTC allowed post-close corporate announcements published between 20:00 and 21:00 UTC to leak into the same-close feature vector.
  - In winter (Eastern Standard Time, UTC-5), 09:30 ET open is **14:30:00 UTC**, not 13:30:00 UTC.
  - `+ 1 day` on Friday targeted Saturday, ignoring weekend closures and Monday holidays.
* **Targeted Correction**:
  - Implemented [`MarketCalendar`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/features/calendar.py) using Python's IANA `America/New_York` timezone.
  - Standard regular close is 16:00 ET $\to$ 20:00:00 UTC (EDT) or 21:00:00 UTC (EST).
  - Early close is 13:00 ET $\to$ 17:00:00 UTC (EDT) or 18:00:00 UTC (EST).
  - Next-session open finds the next valid business day skipping weekends and holidays, converting 09:30 ET to UTC.
  - Verified in [`tests/test_features_calendar.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/tests/test_features_calendar.py): an SEC filing accepted at 20:15 UTC on 2023-05-26 is strictly excluded from the 20:00:00 UTC close decision, and appears only on next open (2023-05-30 13:30:00 UTC).

### 2.2 Concept Alias Prioritization Across Reporting Periods
* **Identified Defect**: In GAAP, companies shifted from `Revenues` to `RevenueFromContractWithCustomerExcludingAssessedTax` after ASC 606 adoption in 2018. Iterating tag by tag and stopping at the first non-empty tag selected historical 2017 facts under `Revenues` rather than the active 2023 facts under the ASC 606 concept.
* **Targeted Correction**:
  - Rewrote [`FundamentalFeatureEngine._extract_latest_concept_fact`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/features/fundamental.py#L126-L163) to collect candidate facts across all specified concept tags, identify the global maximum `period_end`, and use concept priority order solely to break ties within that same latest period.
  - Verified in `test_concept_alias_prioritizes_most_recent_period`: correctly extracts modern 2023 revenue ($383B) over obsolete 2017 revenue ($229B).

### 2.3 Split-Adjusted Price Semantics & Recycled Tickers
* **Stock Split Safety**: Verified that a 4:1 split does not create a false -75% market return; economic return is computed strictly on `adjusted_close`.
* **Identity Isolation**: Verified that two distinct companies sharing the same recycled ticker (`MON`) never compute returns across their corporate boundary.

---

## 3. Storage Policy & Licensing Governance

In response to pre-acceptance audit instructions:
- `FeatureStorageConfig` defaults to `persistence_mode = PersistenceMode.IN_MEMORY` and `storage_authorized = False`.
- In-memory execution message was updated:
  > *"In-Memory Mode: Features retained in volatile RAM. No persistent disk files written. Provider storage authorization remains UNVERIFIED."*
- We do not assert that mathematical transformations grant unrestricted rights. Legal authorization for persistent commercial market quote archives remains **UNVERIFIED** without written enterprise contracts or confirmed academic waivers.

---

## 4. Test Suite Health & Validation Results

The full test suite was executed, achieving 100% green status across all 60 tests:

```text
============================= test session starts =============================
platform win32 -- Python 3.14.6, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\sanja\OneDrive\Documents\Sanjay\Colllege_Projects\Stock_prediction_pinnacle_project\project
plugins: anyio-4.14.1, hydra-core-1.3.4
collected 60 items

tests\test_features_alignment.py .......                                 [ 11%]
tests\test_features_calendar.py ........                                [ 25%]
tests\test_features_fundamental.py ......                                [ 35%]
tests\test_features_market.py .......                                    [ 46%]
tests\test_fnspid_ingestion.py ........                                  [ 60%]
tests\test_sec_ingestion.py ......                                       [ 70%]
tests\test_storage_policy_and_interface.py .........                     [ 85%]
tests\test_tiingo_market.py ...                                          [ 90%]
tests\test_universe.py ......                                            [100%]

============================= 60 passed in 2.75s ==============================
```

---

## 5. Live Bounded Demonstration Output

Executed via [`scripts/demo_phase4a_features.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/scripts/demo_phase4a_features.py):

```text
================================================================================
PHASE 4A — POINT-IN-TIME FEATURE ENGINEERING DEMONSTRATION
================================================================================

[1] Representative Cohort Loaded:
    - Companies: AAPL (US_CIK_0000320193), JPM (US_CIK_0000019617)
    - Market observations: 500 sessions (2023 calendar year)
    - SEC XBRL facts: 3,659 historical facts

[2] Computing Market Technical Features...
    - Generated 500 rows with 58 columns
    - Sample Technical Feature Columns:
trading_date  close  adjusted_close  market_return_1d  market_momentum_21d  market_volatility_21d  market_rsi_14d  market_volume_ratio_20d  market_volatility_21d_missing
  2023-02-02 150.82      148.186671          0.037063             0.205885               0.219933       86.441233                 1.645397                          False
  2023-02-03 154.50      151.802417          0.024400             0.222697               0.226143       88.266327                 2.042008                          False
  2023-02-06 151.73      149.080782         -0.017929             0.213646               0.235780       79.582713                 0.935233                          False

[3] Initializing SEC EDGAR Point-in-Time Fundamental Engine...

[4] Executing Point-in-Time Temporal Alignment (Market + SEC As-Of)...
    - Total harmonized feature rows: 500
    - Total feature matrix dimensions: (500, 147)

[5] Sample Feature Vector Inspection (AAPL at 2023-05-26 20:00:00+00:00):
    * Trading Session: 2023-05-26 (Close: $175.43, Adj Close: $172.87)
    * 1-Day Return: 1.4105%
    * 21-Day Momentum: 4.3133%
    * 21-Day Annualized Volatility: 20.0976%
    * 14-Day RSI: 63.88
    * SEC Available Facts: Revenue=$211,990,000,000 (Period: 2023-04-01, Form: 10-Q)
    * SEC Acceptance Timestamp: 2023-05-05 02:03:52+00:00 (Accession: 0000320193-23-000064)
    * Debt-to-Assets Ratio: 0.8129
    * Net Profit Margin: 0.2555
    * Missing Indicators: Return Missing=False, OCF Missing=False

[6] Point-in-Time Zero-Leakage Audit:
    - Market timestamp violations (> decision_timestamp): 0 (PASS)
    - Fundamental acceptance violations (> decision_timestamp): 0 (PASS)

[7] License-Aware Storage Policy Enforcement:
    * Scenario A (Starter Tier / In-Memory): Persisted=False | In-Memory Mode: Features retained in volatile RAM. No persistent disk files written. Provider storage authorization remains UNVERIFIED.
    * Scenario B (Unauthorized Disk Attempt): Blocked as expected -> 'STORAGE REJECTED: storage_authorized is FALSE. Persistent archiving of derived market features is blocked until explicitly authorized.'

================================================================================
PHASE 4A DEMONSTRATION COMPLETE: ALL INTEGRITY & LEGAL SAFEGUARDS VERIFIED
================================================================================
```

---

## 6. Phase 4A Acceptance Criteria Scorecard

| Acceptance Criterion | Requirement | Status | Evidence / Verification |
| :--- | :--- | :---: | :--- |
| **Criterion 1: Modular Feature Engines** | Technical & fundamental feature generators under `src/features/` | **PASS** | [`market.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/features/market.py) & [`fundamental.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/features/fundamental.py). |
| **Criterion 2: Timezone & Exchange Calendar** | America/New_York DST, regular & early closes, next-session open | **PASS** | Implemented [`calendar.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/features/calendar.py); verified in `test_features_calendar.py`. |
| **Criterion 3: Point-in-Time Safety** | 0 look-ahead violations; post-close filings excluded from same close | **PASS** | Verified in `test_post_close_sec_filing_strictly_excluded_from_same_close_decision`. |
| **Criterion 4: Concept Alias Modernization** | Global `period_end` max prevents obsolete GAAP tag selection | **PASS** | Verified in `test_concept_alias_prioritizes_most_recent_period`. |
| **Criterion 5: Split & Identity Isolation** | Adjusted returns across splits; corporate identity boundary isolation | **PASS** | Verified in `test_stock_split_adjusted_returns` & `test_recycled_ticker_isolation`. |
| **Criterion 6: Missing Fact Preservation** | Missing concepts preserved as `NaN`; ratios not invented | **PASS** | Verified in `test_missing_facts_are_nan_not_zero` and `test_ratio_computation_and_no_invention`. |
| **Criterion 7: Storage Policy Governance** | Persistence blocked by default; licensing treated as UNVERIFIED | **PASS** | Implemented [`storage.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/features/storage.py); verified in `TestStoragePolicyEnforcement`. |
| **Criterion 8: Full Test Suite Regression** | 100% green status across unit and integration tests | **PASS** | **60 of 60 tests passing** in 2.75s with 0 warnings. |
| **Criterion 9: Scope Discipline** | No full downloads, no model training, no UI, no label generation | **PASS** | Strict stop conditions preserved. |

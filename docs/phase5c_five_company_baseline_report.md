# Phase 5C — Multi-Company Market-Only Baseline Report

**Date:** 2026-10-16  
**Status:** Completed & Audited — Conditional Multi-Company Baseline Established  
**Artifacts Produced:**  
- `src/features/target.py` (`ForwardReturnTargetEngine`)  
- `src/models/splitter.py` (`WalkForwardSplitter`, `WalkForwardConfig`)  
- `src/models/baseline.py` (`MarketBaselinePipeline`)  
- `tests/test_target_and_baseline.py` (12 unit and panel regression tests, 112 total passing test suite)

---

## 1. Data Inventory & Identity Audit

We performed a direct, empirical inspection of the actual market dataset (`data/processed/market/sp500_market_sample.parquet`) and the canonical S&P 500 company universe (`data/processed/universe/sp500_universe.parquet`).

### 1.1 Market Dataset Properties (`sp500_market_sample.parquet`)
- **Total Records**: 45,770 rows $\times$ 11 columns
- **Columns**: `company_id`, `ticker`, `timestamp`, `trading_date`, `open`, `high`, `low`, `close`, `adjusted_close`, `volume`, `source`
- **Missing Values**: Exactly **0** nulls across all 11 columns.
- **Duplicate Records**: Exactly **0** duplicate `(ticker, trading_date)` rows.

### 1.2 Company Identity & Historical Mapping Breakdown

| Ticker | Company ID | Historical S&P 500 Company Name | CIK | S&P 500 Membership Interval | Date Range in Sample | Rows in Sample | Invalid Prices ($\le 0$) | Usable Status & Exclusion Rationale |
| :---: | :---: | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **AA** | `UNKNOWN_AA` | *Unverified Historical Entity* | None | *Not in Canonical Index* | 1962-01-02 $\to$ 2023-12-28 | 15,605 | 0 | **EXCLUDED**. Ticker `AA` historically represented Alcoa Inc. prior to its November 2016 corporate split into Alcoa Corp and Arconic Inc. The entity has no CIK or verified membership interval in `sp500_universe.parquet`. Excluded to prevent identity contamination. |
| **AAPL** | `US_CIK_0000320193` | Apple Inc. | `0000320193` | `[1996-01-02, None)` | 1980-12-12 $\to$ 2023-12-28 | 10,852 | 0 | **ELIGIBLE & INCLUDED**. Full history, zero invalid prices. |
| **JPM** | `US_CIK_0000019617` | JPMorgan Chase | `0000019617` | `[1996-01-02, None)` | 1980-03-17 $\to$ 2023-12-28 | 11,040 | 959 (Open = 0.0 in 1980–1983) | **ELIGIBLE & INCLUDED**. 959 records from 1980–1983 contain zero open prices (`open == 0.0`). The period from `1983-12-30` to `2023-12-28` contains 10,081 clean, positive price records. |
| **GOOG** | `US_CIK_0001652044` | Alphabet Inc. (Class C) | `0001652044` | `[2014-04-03, None)` | 2004-08-19 $\to$ 2023-12-28 | 4,874 | 0 | **ELIGIBLE & INCLUDED**. Full clean history from IPO. |
| **TSLA** | `US_CIK_0001318605` | Tesla, Inc. | `0001318605` | `[2020-12-21, None)` | 2010-06-29 $\to$ 2023-12-28 | 3,399 | 0 | **ELIGIBLE & INCLUDED**. Full clean history from IPO. (Constituent since December 2020). |

**Common Overlap Across the 4 Verified Companies**:
- The common chronological date intersection spanning all 4 companies (`AAPL`, `JPM`, `GOOG`, `TSLA`) is **3,399 trading days** from **June 29, 2010 to December 28, 2023**.

---

## 2. Target-Price Correctness & Adjustment Audit

### 2.1 Pricing Convention & Derivation
The target engine computes the 5-session forward return:
$$y_{T}^{(5)} = \frac{P_{T+5, \text{close}}^{\text{adj}} - P_{T+1, \text{open}}^{\text{adj}}}{P_{T+1, \text{open}}^{\text{adj}}}$$

Because `sp500_market_sample.parquet` provides `open`, `close`, and `adjusted_close` (lacking `adjusted_open`), the adjusted open price is derived via:
$$\text{adj\_factor}_{t} = \frac{P_{t, \text{close}}^{\text{adj}}}{P_{t, \text{close}}}, \quad P_{t, \text{open}}^{\text{adj}} = P_{t, \text{open}} \times \text{adj\_factor}_{t}$$

### 2.2 Verification Against Major Corporate Actions
1. **Apple 4-for-1 Split (August 31, 2020)**:
   - On August 28, 2020: raw open $126.01, close $124.81, adjusted close $122.43. $\text{adj\_factor} = 0.980953$.
   - On August 31, 2020: raw open $127.58, close $129.04, adjusted close $126.58. $\text{adj\_factor} = 0.980953$.
   - The adjustment factor remains perfectly smooth across the split date, yielding true economic holding return without step-drops.
2. **Tesla 5-for-1 Split (August 31, 2020)**:
   - In the sample, Tesla's prices pre-August 2020 were already split-adjusted at ingestion, producing continuous adjusted returns across the split.
3. **Terminal Horizon Masking**:
   - For every company independently, the last $H = 5$ trading sessions have unavailable future exit prices ($T+5 > N$).
   - `ForwardReturnTargetEngine` masks these rows strictly with `target_forward_return_5d_valid = False` and `target_forward_return_5d = NaN`. Zero synthetic or imputed future prices are permitted.

---

## 3. Four-Company Panel Dataset Construction

Using `UnifiedDatasetBuilder` and `ForwardReturnTargetEngine`, we constructed a consistent market-only panel across the 4 verified companies over the benchmark window (`2019-01-01` to `2020-06-10`):

- **Input Cohort Filter**: `('US_CIK_0000320193', 'US_CIK_0000019617', 'US_CIK_0001652044', 'US_CIK_0001318605')`
- **Total Aligned Sessions**: **1,452 observations** (exactly 363 trading sessions $\times$ 4 companies).
- **Row Identifier Uniqueness**: 100% unique `(company_id, decision_timestamp)` pairs (`dataset_row_id`).
- **Target Validity per Company**:
  - `AAPL`: 358 valid targets, exactly 5 terminal rows masked.
  - `JPM`: 358 valid targets, exactly 5 terminal rows masked.
  - `GOOG`: 358 valid targets, exactly 5 terminal rows masked.
  - `TSLA`: 358 valid targets, exactly 5 terminal rows masked.
  - **Total Valid Labeled Panel**: **1,432 rows** across **358 unique calendar dates**.

---

## 4. Fair Walk-Forward Baseline Evaluation

### 4.1 Chronological Evaluation Protocol
- **Split Parameters**: `n_splits = 4`, `train_min_sessions = 173`, `val_sessions = 45`, `purge_sessions = 5`.
- **Panel Invariant**: Every calendar trading date contains all 4 companies. Walk-forward partitions operate on sorted calendar dates, ensuring all 4 companies for date $t$ are assigned simultaneously to train, purge, or validation.
- **Purge Enforcement**: A mandatory **5-session gap** (20 rows across 4 companies) separates every training fold end from validation start.
- **Preprocessing Isolation**: `SimpleImputer(strategy="median")` and `StandardScaler()` are fitted **strictly on the training fold**. Validation features are transformed using parameters frozen from training.
- **Aggregation Convention**: Because each validation fold contains exactly 45 sessions per company (180 total observations), equal weighting across companies is mathematically guaranteed (each company represents exactly 25.0% of the validation observations).

### 4.2 Comprehensive Results Across All 4 Folds

#### Fold 0 (Train: `2019-01-02` $\to$ `2019-09-09` [692 rows] | Purge: 5 days | Val: `2019-09-17` $\to$ `2019-11-18` [180 rows])
- **Selected Ridge $\alpha$**: `1000.0`
- **Descriptive IC**: `-0.101`

| Model / Baseline | Aggregate RMSE | Aggregate MAE | Aggregate Hit Rate | AAPL MAE (Hit) | JPM MAE (Hit) | GOOG MAE (Hit) | TSLA MAE (Hit) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Reference 0 (Zero Return)** | 0.0486 | 0.0300 | 50.00% | 0.0215 (50.0%) | 0.0210 (50.0%) | 0.0162 (50.0%) | 0.0613 (50.0%) |
| **Reference 1 (Historical Median)** | **0.0464** | **0.0277** | **70.56%** | **0.0180 (77.8%)** | **0.0194 (66.7%)** | **0.0144 (71.1%)** | **0.0589 (66.7%)** |
| **Model 1 (Market-Only Ridge)** | 0.0485 | 0.0295 | 62.78% | 0.0200 (75.6%) | 0.0201 (64.4%) | 0.0151 (68.9%) | 0.0626 (42.2%) |

#### Fold 1 (Train: `2019-01-02` $\to$ `2019-11-11` [872 rows] | Purge: 5 days | Val: `2019-11-19` $\to$ `2020-01-24` [180 rows])
- **Selected Ridge $\alpha$**: `1000.0`
- **Descriptive IC**: `+0.304`

| Model / Baseline | Aggregate RMSE | Aggregate MAE | Aggregate Hit Rate | AAPL MAE (Hit) | JPM MAE (Hit) | GOOG MAE (Hit) | TSLA MAE (Hit) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Reference 0 (Zero Return)** | 0.0481 | 0.0317 | 50.00% | 0.0242 (50.0%) | **0.0134 (50.0%)** | 0.0192 (50.0%) | 0.0701 (50.0%) |
| **Reference 1 (Historical Median)** | 0.0445 | 0.0289 | **72.22%** | **0.0190 (82.2%)** | 0.0139 (53.3%) | **0.0176 (68.9%)** | 0.0650 (84.4%) |
| **Model 1 (Market-Only Ridge)** | **0.0426** | **0.0281** | **72.22%** | 0.0195 (82.2%) | 0.0136 (53.3%) | 0.0178 (68.9%) | **0.0615 (84.4%)** |

#### Fold 2 (Train: `2019-01-02` $\to$ `2020-01-16` [1052 rows] | Purge: 5 days | Val: `2020-01-27` $\to$ `2020-03-30` [180 rows, COVID Crash])
- **Selected Ridge $\alpha$**: `100.0`
- **Descriptive IC**: `-0.078`

| Model / Baseline | Aggregate RMSE | Aggregate MAE | Aggregate Hit Rate | AAPL MAE (Hit) | JPM MAE (Hit) | GOOG MAE (Hit) | TSLA MAE (Hit) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Reference 0 (Zero Return)** | **0.1170** | **0.0796** | **50.00%** | **0.0498 (50.0%)** | **0.0640 (50.0%)** | **0.0435 (50.0%)** | **0.1611 (50.0%)** |
| **Reference 1 (Historical Median)** | 0.1189 | 0.0819 | 42.78% | 0.0520 (42.2%) | 0.0680 (35.6%) | 0.0448 (48.9%) | 0.1626 (44.4%) |
| **Model 1 (Market-Only Ridge)** | 0.1244 | 0.0847 | **50.00%** | 0.0507 (53.3%) | 0.0648 (53.3%) | 0.0451 (51.1%) | 0.1784 (42.2%) |

#### Fold 3 (Holdout) (Train: `2019-01-02` $\to$ `2020-03-23` [1232 rows] | Purge: 5 days | Val: `2020-03-31` $\to$ `2020-06-03` [180 rows, Rebound])
- **Selected Ridge $\alpha$**: `1000.0`
- **Descriptive IC**: `-0.155`

| Model / Baseline | Aggregate RMSE | Aggregate MAE | Aggregate Hit Rate | AAPL MAE (Hit) | JPM MAE (Hit) | GOOG MAE (Hit) | TSLA MAE (Hit) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Reference 0 (Zero Return)** | 0.0773 | 0.0536 | 50.00% | 0.0393 (50.0%) | 0.0619 (50.0%) | 0.0290 (50.0%) | 0.0842 (50.0%) |
| **Reference 1 (Historical Median)** | 0.0738 | 0.0502 | **72.78%** | 0.0347 (82.2%) | **0.0606 (60.0%)** | **0.0251 (75.6%)** | 0.0806 (73.3%) |
| **Model 1 (Market-Only Ridge)** | **0.0732** | **0.0497** | 70.00% | **0.0332 (82.2%)** | **0.0606 (60.0%)** | 0.0265 (64.4%) | **0.0786 (73.3%)** |

---

## 5. Critical Findings & Honest Comparative Insights

1. **Ridge Does NOT Systematically Outperform Naive Baselines**:
   - In Fold 0, the simple Historical Median beats Ridge on both RMSE (0.0464 vs 0.0485) and MAE (0.0277 vs 0.0295).
   - In Fold 2 (the March 2020 crash), Reference 0 (Zero Return) outperforms both Median and Ridge (MAE 0.0796 vs 0.0847), because positive trailing equity momentum failed to anticipate catastrophic downside volatility.
   - Only in Fold 1 and Fold 3 does Ridge show marginal improvement over naive median (MAE 0.0281 vs 0.0289 in Fold 1; 0.0497 vs 0.0502 in Fold 3).
2. **Volatile Assets Dominate Aggregate Error**:
   - TSLA error (MAE 0.06 to 0.17) is $3\times$ to $4\times$ larger than GOOG error (MAE 0.015 to 0.045).
   - Equal-weighted averaging ensures TSLA does not distort the evaluation count, but reporting per-company metrics is essential to understand individual asset predictability.
3. **Information Coefficient Rank Correlation is Weak / Unstable**:
   - Cross-sectional/temporal IC fluctuates widely across regimes: $-0.101$ in Fold 0, $+0.304$ in Fold 1, $-0.078$ in Fold 2, and $-0.155$ in Fold 3.
   - This proves that market-only linear indicators provide negligible persistent rank-order alpha.

---

## 6. Preservation of Research Boundaries

- **Ticker `AA` Exclusion**: Excluded cleanly from model training due to unverified identity (`UNKNOWN_AA`).
- **Data Licensing**: Yahoo-derived market data is treated strictly as an internal prototype resource.
- **Tiingo Disk Persistence**: `storage_authorized = False` remains enforced; no persistent database writes were performed.
- **News Isolation**: Zero news features or sentiment scores were included in this market-only prototype.

---

## 7. Automated Test Suite Execution

Ran complete pytest test suite:
```powershell
python -m pytest
```
**Outcome**: **112 passed in 20.85s** (zero failures, zero warnings across all 12 modules):
- `tests/test_target_and_baseline.py`: 12 passed (+3 new panel tests)
- `tests/test_dataset_builder.py`: 24 passed
- `tests/test_features_alignment.py`: 7 passed
- `tests/test_features_calendar.py`: 8 passed
- `tests/test_features_fundamental.py`: 6 passed
- `tests/test_features_market.py`: 7 passed
- `tests/test_fnspid_ingestion.py`: 8 passed
- `tests/test_news_features.py`: 16 passed
- `tests/test_sec_ingestion.py`: 6 passed
- `tests/test_storage_policy_and_interface.py`: 9 passed
- `tests/test_tiingo_market.py`: 3 passed
- `tests/test_universe.py`: 6 passed

---

## 8. Go / No-Go Decision for Next Phase

### Decision: **CONDITIONAL GO**
- **GO** for Phase 5D: Incorporating Point-in-Time SEC EDGAR Fundamental Features alongside Market Features to test whether fundamental valuation (revenue growth, margins, P/E ratios) improves directional prediction beyond the naive median baseline.
- **NO-GO** for production deployment, live trading, investment recommendations, or commercial redistribution of prototype market data.

Phase 5C is complete. We have stopped here and are waiting for your review.

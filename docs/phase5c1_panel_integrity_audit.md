# Phase 5C.1 — Panel Splitter and Target Integrity Audit Report

**Date:** 2026-10-16  
**Status:** Audit Completed & Verified — Zero Defects Found, Programmatic Integrity Confirmed  
**Artifacts Produced / Updated:**  
- `docs/phase5c1_panel_integrity_audit.md` (this report)  
- `tests/test_target_and_baseline.py` (added `test_five_date_panel_purge_and_zero_label_overlap`, 113 total passing test suite)

---

## 1. Panel-Aware Chronological Splitting Audit

We inspected `src/models/splitter.py`, `WalkForwardSplitter`, `WalkForwardConfig`, and the multi-company panel dataset.

### 1.1 Architecture & Calendar-Date Partitioning
`WalkForwardSplitter` operates strictly on **unique chronological trading dates** rather than raw row counts:
```python
unique_dates = pd.Series(df[date_col].unique())
# Splits are computed as integer date index slices:
train_dates = set(unique_dates.iloc[:train_end_idx])
val_dates = set(unique_dates.iloc[val_start_idx:val_end_idx])
# Row indices are extracted by filtering against those unique calendar dates:
train_idx = df.index[df[date_col].isin(train_dates)].to_numpy()
val_idx = df.index[df[date_col].isin(val_dates)].to_numpy()
```
Because `df[date_col].isin(...)` is evaluated across the entire panel, all 4 companies for any given calendar date are grouped together atomically into the same partition.

### 1.2 Programmatic Audit Across All 4 Folds
The panel comprises **1,432 valid labeled observations** spanning **358 unique calendar dates** (`2019-01-02` to `2020-06-03`) across 4 verified companies (`AAPL`, `JPM`, `GOOG`, `TSLA`).

| Fold | Section | Unique Dates | Calendar Date Range | Total Rows | Companies per Date | Exit / Decision Feasibility Verification |
| :---: | :--- | :---: | :---: | :---: | :---: | :--- |
| **0** | **Training**<br>**Purge Gap**<br>**Validation** | **173**<br>**5**<br>**45** | 2019-01-02 $\to$ 2019-09-09<br>2019-09-10 $\to$ 2019-09-16<br>2019-09-17 $\to$ 2019-11-18 | 692<br>20<br>180 | 4 on every date<br>4 on every date<br>4 on every date | - **Last Train Target Exit**: `2019-09-16`<br>- **First Val Decision**: `2019-09-17`<br>- **Outcome Overlap**: **Zero** ($2019\text{-}09\text{-}16 < 2019\text{-}09\text{-}17$) |
| **1** | **Training**<br>**Purge Gap**<br>**Validation** | **218**<br>**5**<br>**45** | 2019-01-02 $\to$ 2019-11-11<br>2019-11-12 $\to$ 2019-11-18<br>2019-11-19 $\to$ 2020-01-24 | 872<br>20<br>180 | 4 on every date<br>4 on every date<br>4 on every date | - **Last Train Target Exit**: `2019-11-18`<br>- **First Val Decision**: `2019-11-19`<br>- **Outcome Overlap**: **Zero** ($2019\text{-}11\text{-}18 < 2019\text{-}11\text{-}19$) |
| **2** | **Training**<br>**Purge Gap**<br>**Validation** | **263**<br>**5**<br>**45** | 2019-01-02 $\to$ 2020-01-16<br>2020-01-17 $\to$ 2020-01-24<br>2020-01-27 $\to$ 2020-03-30 | 1052<br>20<br>180 | 4 on every date<br>4 on every date<br>4 on every date | - **Last Train Target Exit**: `2020-01-24`<br>- **First Val Decision**: `2020-01-27`<br>- **Outcome Overlap**: **Zero** ($2020\text{-}01\text{-}24 < 2020\text{-}01\text{-}27$) |
| **3 (Holdout)** | **Training**<br>**Purge Gap**<br>**Validation** | **308**<br>**5**<br>**45** | 2019-01-02 $\to$ 2020-03-23<br>2020-03-24 $\to$ 2020-03-30<br>2020-03-31 $\to$ 2020-06-03 | 1232<br>20<br>180 | 4 on every date<br>4 on every date<br>4 on every date | - **Last Train Target Exit**: `2020-03-30`<br>- **First Val Decision**: `2020-03-31`<br>- **Outcome Overlap**: **Zero** ($2020\text{-}03\text{-}30 < 2020\text{-}03\text{-}31$) |

### 1.3 Programmatic Invariants Verified
1. **Chronological Disjointness**: For every fold, $\text{set}(\text{Train Dates}) \cap \text{set}(\text{Purge Dates}) = \emptyset$, $\text{set}(\text{Train Dates}) \cap \text{set}(\text{Val Dates}) = \emptyset$, and $\text{set}(\text{Purge Dates}) \cap \text{set}(\text{Val Dates}) = \emptyset$.
2. **Purge Date Count**: Exactly **5 complete trading dates** (20 panel rows) are purged between training and validation in every fold.
3. **Atomic Company Grouping**: Exactly **4 companies** are present on every single validation date. No company is split across train/validation boundaries.
4. **Zero Target Outcome Overlap**: In every fold, the exit date of the very last training target is strictly earlier than the first validation decision date ($\text{Last Train Target Exit} < \text{First Val Decision Date}$). Training target returns can never observe prices from the validation period.
5. **Holdout Isolation**: Fold 3 (`2020-03-31` to `2020-06-03`) remains strictly out-of-sample and was never observed during hyperparameter selection in Folds 0, 1, or 2.

---

## 2. Target-Price Adjustment & Corporate Action Invariance

### 2.1 Derivation Method
In `ForwardReturnTargetEngine` (`src/features/target.py`), the 5-session forward return is defined as:
$$y_{T}^{(5)} = \frac{P_{T+5, \text{close}}^{\text{adj}} - P_{T+1, \text{open}}^{\text{adj}}}{P_{T+1, \text{open}}^{\text{adj}}}$$
Where:
$$\text{adj\_factor}_{t} = \frac{P_{t, \text{close}}^{\text{adj}}}{P_{t, \text{close}}}, \quad P_{t, \text{open}}^{\text{adj}} = P_{t, \text{open}} \times \text{adj\_factor}_{t}$$

### 2.2 Verification Against Major Corporate Actions
1. **Apple 4-for-1 Split (August 31, 2020)**:
   - Evaluated the split boundary: August 28 close was $124.81 (adj $122.43), August 31 open was $127.58 (adj $125.15), and August 31 close was $129.04 (adj $126.58).
   - $\text{adj\_factor} = 0.980953$ is constant on both sides of the split date.
   - Resulting economic holding return across the split boundary is $+3.39\%$, completely free of artificial split drops.
2. **Tesla 5-for-1 Split (August 31, 2020)**:
   - In `sp500_market_sample.parquet`, Tesla quotes prior to August 2020 were already split-adjusted at data ingestion, producing continuous adjusted returns across the split.
3. **Documented Source Limitations**:
   - The S&P 500 market sample (`sp500_market_sample.parquet`) originates from Yahoo Finance scraping via `yfinance` in early phases. While Yahoo adjusts close prices backwards for splits and dividends, intraday low/high/open prices in scraped Yahoo tables are pre-adjusted for splits but unadjusted for historical cash dividends.
   - Deriving $P_{t, \text{open}}^{\text{adj}} = P_{t, \text{open}} \times (\frac{P_{t, \text{close}}^{\text{adj}}}{P_{t, \text{close}}})$ correctly applies the cash dividend adjustment factor to open prices, ensuring entry and exit prices are on an identical dividend-reinvested scale.
   - However, because the upstream provider is an unverified academic prototype scrape, this data **cannot be claimed as a commercially verified institutional audit archive**.

---

## 3. Reputed Reproducibility Evaluation

Rerunning all 4 chronological walk-forward folds across the 3 baseline models confirms the exact stability of the Phase 5C evaluation metrics:

| Fold | Validation Period (N = 180 rows) | Model | Aggregate RMSE | Aggregate MAE | Aggregate Hit Rate | Descriptive IC | Selected $\alpha$ |
| :---: | :---: | :--- | :---: | :---: | :---: | :---: | :---: |
| **0** | 2019-09-17 $\to$ 2019-11-18 | Reference 0 (Zero Return)<br>**Reference 1 (Historical Median)**<br>Model 1 (Ridge) | 0.0486<br>**0.0464**<br>0.0485 | 0.0300<br>**0.0277**<br>0.0295 | 50.00%<br>**70.56%**<br>62.78% | N/A<br>N/A<br>-0.101 | N/A<br>N/A<br>1000.0 |
| **1** | 2019-11-19 $\to$ 2020-01-24 | Reference 0 (Zero Return)<br>Reference 1 (Historical Median)<br>**Model 1 (Ridge)** | 0.0481<br>0.0445<br>**0.0426** | 0.0317<br>0.0289<br>**0.0281** | 50.00%<br>**72.22%**<br>**72.22%** | N/A<br>N/A<br>+0.304 | N/A<br>N/A<br>1000.0 |
| **2** | 2020-01-27 $\to$ 2020-03-30 (Crash) | **Reference 0 (Zero Return)**<br>Reference 1 (Historical Median)<br>Model 1 (Ridge) | **0.1170**<br>0.1189<br>0.1244 | **0.0796**<br>0.0819<br>0.0847 | **50.00%**<br>42.78%<br>**50.00%** | N/A<br>N/A<br>-0.078 | N/A<br>N/A<br>100.0 |
| **3** | 2020-03-31 $\to$ 2020-06-03 (Holdout) | Reference 0 (Zero Return)<br>Reference 1 (Historical Median)<br>**Model 1 (Ridge)** | 0.0773<br>0.0738<br>**0.0732** | 0.0536<br>0.0502<br>**0.0497** | 50.00%<br>**72.78%**<br>70.00% | N/A<br>N/A<br>-0.155 | N/A<br>N/A<br>1000.0 |

---

## 4. Automated Regression Tests

We added a dedicated panel audit regression test in `tests/test_target_and_baseline.py`:
- `test_five_date_panel_purge_and_zero_label_overlap`: Programmatically asserts that across multi-company panels, exactly 5 calendar trading dates are purged, all companies remain grouped on each date, and the last training target exit date is strictly prior to the first validation decision date.

Running the full automated test suite:
```powershell
python -m pytest
```
**Outcome**: **113 passed in 21.22s** (zero failures, zero warnings across all 12 test modules).

---

## 5. Final Recommendation

### Decision: **CONDITIONAL GO**
- The panel walk-forward partition, 5-date purge gap, company grouping, and zero label overlap are verified and programmatically guaranteed.
- **GO** for Phase 5D: Integrating point-in-time SEC EDGAR fundamental features (revenues, net income, balance sheet ratios) alongside market technical features to evaluate whether fundamental signals provide genuine excess predictive power over naive historical baselines.
- **NO-GO** for production trading, investment recommendations, or commercial deployment of the prototype pipeline.

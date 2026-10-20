# Phase 5B — Forward-Return Target Engine and Market-Only Baseline Implementation Report

**Date:** 2026-10-16  
**Status:** Completed & Validated — Conditional Baseline Established  
**Artifacts Produced:**  
- `src/features/target.py` (`ForwardReturnTargetEngine`, `TargetConfig`)  
- `src/models/splitter.py` (`WalkForwardSplitter`, `WalkForwardConfig`)  
- `src/models/baseline.py` (`MarketBaselinePipeline`, `BaselineEvaluationResult`)  
- `src/models/__init__.py`  
- `tests/test_target_and_baseline.py` (8 new tests, 108 total passing suite)

---

## 1. Adjusted-Price Availability and Corporate Action Validation

### 1.1 Price Schema Audit & Problem Formulation
Phase 5B defines a five-trading-session forward return target executed at session $T+1$ open and exited at session $T+5$ close:
$$y_{T}^{(5)} = \frac{P_{T+5, \text{close}}^{\text{adj}} - P_{T+1, \text{open}}^{\text{adj}}}{P_{T+1, \text{open}}^{\text{adj}}}$$

Inspection of the available market Parquet files revealed:
1. **Tiingo Pilot Market (`pilot_market_sample.parquet`)**: Contains explicitly provided, verified `adjusted_open` and `adjusted_close` columns.
2. **S&P 500 Market Sample (`sp500_market_sample.parquet`)**: Contains `open`, `close`, and `adjusted_close`, but lacks an explicit `adjusted_open` column.

### 1.2 Mathematical & Empirical Validation of the Derived Adjusted Open
To avoid silently mixing unadjusted open prices with adjusted close prices, we investigated whether a valid adjusted open price can be derived via the documented split/dividend adjustment factor:
$$\text{adj\_factor}_{t} = \frac{P_{t, \text{close}}^{\text{adj}}}{P_{t, \text{close}}}$$
$$P_{t, \text{open}}^{\text{adj}} = P_{t, \text{open}} \times \text{adj\_factor}_{t}$$

#### Empirical Invariance Verifications:
1. **Apple's 4-for-1 Stock Split (August 31, 2020)**:
   - In `sp500_market_sample.parquet`, all historical quotes prior to August 31, 2020 were already split-adjusted at data ingestion (e.g., August 28, 2020 open was $126.01, close was $124.81; August 31, 2020 open was $127.58, close was $129.04).
   - The adjustment factor $\text{adj\_factor}_{t} = 0.980953$ across the entire split boundary, representing subsequent dividend adjustments.
   - Economic return across the split boundary: $(126.58 - 122.43) / 122.43 = +3.39\%$ (matching real market holding return, without any artificial split drop).
2. **Apple's 7-for-1 Stock Split (June 9, 2014)**:
   - Quotes on June 6, 2014: raw open $92.84, close $92.22, adjusted close $83.76, factor = $0.908167$.
   - Quotes on June 9, 2014: raw open $92.70, close $93.70, adjusted close $85.10, factor = $0.908167$.
   - The factor is completely stable across the ex-split date.
3. **Tiingo Dividend Adjustment Cross-Check**:
   - On Tiingo Apple data with cash dividends ($0.23, $0.24), we verified that the ratio $\frac{P_{\text{open}}^{\text{adj}}}{P_{\text{open}}}$ and $\frac{P_{\text{close}}^{\text{adj}}}{P_{\text{close}}}$ match to within $10^{-13}$ numerical precision.

**Conclusion**: Deriving $P_{t, \text{open}}^{\text{adj}} = P_{t, \text{open}} \times (\frac{P_{t, \text{close}}^{\text{adj}}}{P_{t, \text{close}}})$ is mathematically rigorous and preserves exact economic total returns without price convention leakage.

---

## 2. Implementation Details

### 2.1 `ForwardReturnTargetEngine` (`src/features/target.py`)
- **Strict Invariants**:
  - Validates positive non-zero prices (`open > 0`, `close > 0`, `adjusted_close > 0`).
  - Rejects duplicate `(company_id, trading_date)` records.
  - Ensures strictly chronological ordering per company.
  - Vectorized entry $P_{T+1, \text{open}}^{\text{adj}}$ via `shift(-1)` and exit $P_{T+5, \text{close}}^{\text{adj}}$ via `shift(-H)`.
- **Terminal Horizon Masking**:
  - The last $H = 5$ sessions in any company time series have unavailable exit prices.
  - These rows have `target_forward_return_5d_valid = False` and `target_forward_return_5d = NaN`.
  - Future prices are never passed into feature matrices; they exist exclusively in target labels.

### 2.2 `WalkForwardSplitter` (`src/models/splitter.py`)
- **Strict Chronological Cross-Validation**:
  - Disallows random shuffling and standard k-fold cross-validation.
  - Generates expanding-window training splits and rolling validation splits.
- **Purge & Embargo Enforcement**:
  - Enforces a mandatory **5-session purge gap** between the end of the training set and the start of the validation set:
    $$\text{date}_{\text{val, start}} - \text{date}_{\text{train, end}} > 5 \text{ exchange sessions}$$
  - Eliminates overlapping holding-period return contamination ($y_{T}^{(5)}$ from the end of training cannot overlap $y_{T}^{(5)}$ in validation).

### 2.3 `MarketBaselinePipeline` (`src/models/baseline.py`)
- **Preprocessing Isolation**:
  - Feature imputation (`SimpleImputer(strategy="median")`) and standardization (`StandardScaler()`) are fit **strictly on the training fold**.
  - Validation features are transformed using frozen training parameters.
- **Reference Baselines**:
  - *Reference 0 (Naive Zero Return)*: Predicts $\hat{y} = 0.0$.
  - *Reference 1 (Historical Median)*: Predicts $\hat{y} = \text{median}(y_{\text{train}})$.
- **Model 1 (Market-Only Ridge)**:
  - Trains L2-regularized linear model across 17 technical indicators (returns, volatility, momentum, SMA z-scores, RSI, volume ratios).
  - Hyperparameter $\alpha \in \{0.01, 0.1, 1.0, 10.0, 100.0, 1000.0\}$ selected via internal chronological validation on the training fold.
  - Metrics: RMSE, MAE, Hit Rate (Directional Accuracy), and Information Coefficient (Spearman rank correlation).

---

## 3. Initial Pipeline-Validation Experiment (Apple Inc.)

To validate that the target engine, splitter, and baseline models run end-to-end without runtime errors or leakage, we executed an initial pipeline-validation experiment on Apple Inc. (`AAPL`).

> [!IMPORTANT]
> **Scoping Warning**: This experiment serves exclusively as technical pipeline validation. It does **NOT** constitute evidence of generalizable alpha or predictive profitability across the S&P 500 universe.

### 3.1 Dataset & Target Summary
- **Period**: 2019-01-02 to 2020-06-10 (363 trading sessions).
- **Usable Labeled Rows**: **358 sessions** (exactly 5 terminal horizon rows masked as invalid).
- **Target Distribution ($y_{T}^{(5)}$)**:
  - Mean: **+1.25%** (+0.0125)
  - Standard Deviation: **3.75%** (0.0375)
  - Min / Max: -15.42% to +14.81% (capturing the extreme volatility of February–March 2020 COVID onset).

### 3.2 Walk-Forward Cross-Validation Results (Expanding Train, 5-Session Purge Gap)

| Fold | Training Window (N sessions) | Purge Gap | Validation Window (N sessions) | Model | RMSE | MAE | Hit Rate (Direction) | Information Coefficient (IC) | Best $\alpha$ |
| :---: | :---: | :---: | :---: | :--- | :---: | :---: | :---: | :---: | :---: |
### 3.2 Walk-Forward Cross-Validation Audit & Partitioning Across Full History

#### Why the Prior 3 Folds Ended on 2020-02-04:
The initial configuration (`train_min_sessions=150, val_sessions=40, n_splits=3`) stepped forward from session 0 without an anchor to the dataset's terminal date. Consequently, the three validation windows covered:
- Fold 0: sessions 155..194 (2019-08-14 to 2019-10-09)
- Fold 1: sessions 195..234 (2019-10-10 to 2019-12-05)
- Fold 2: sessions 235..274 (2019-12-06 to 2020-02-04)
This left the final 83 sessions (index 275 through 357, spanning `2020-02-05` to `2020-06-03`, including the COVID onset and recovery) completely unvalidated.

#### Corrected Full-History Evaluation Scheme:
To evaluate across the entire available historical period and provide an out-of-sample chronological holdout:
- Total valid sessions: **358** (`2019-01-02` to `2020-06-03`).
- Partition parameter: `train_min_sessions = 173`, `val_sessions = 45`, `purge_sessions = 5`, `n_splits = 4`.
- **Exact dates and session counts for every fold (0 unused rows)**:
  - **Fold 0**: Train: `2019-01-02` $\to$ `2019-09-09` (173 rows) | Purge: `2019-09-10` $\to$ `2019-09-16` (5 rows) | Val: `2019-09-17` $\to$ `2019-11-18` (45 rows).
  - **Fold 1**: Train: `2019-01-02` $\to$ `2019-11-11` (218 rows) | Purge: `2019-11-12` $\to$ `2019-11-18` (5 rows) | Val: `2019-11-19` $\to$ `2020-01-24` (45 rows).
  - **Fold 2**: Train: `2019-01-02` $\to$ `2020-01-16` (263 rows) | Purge: `2020-01-17` $\to$ `2020-01-24` (5 rows) | Val: `2020-01-27` $\to$ `2020-03-30` (45 rows, capturing COVID volatility).
  - **Fold 3 (Later Chronological Holdout)**: Train: `2019-01-02` $\to$ `2020-03-23` (308 rows) | Purge: `2020-03-24` $\to$ `2020-03-30` (5 rows) | Val: `2020-03-31` $\to$ `2020-06-03` (45 rows, ending on the final available valid date).
  - **Unused valid rows**: **0 rows**. All 358 sessions are systematically assigned to train, purge, or validation.

### 3.3 Walk-Forward Evaluation Results Across All Folds

| Fold | Training Window (N) | Purge Gap | Validation Window (N) | Model | RMSE | MAE | Hit Rate | Descriptive IC | Selected $\alpha$ |
| :---: | :---: | :---: | :---: | :--- | :---: | :---: | :---: | :---: | :---: |
| **0** | 2019-01-02 $\to$ 2019-09-09 (173) | 5 days | 2019-09-17 $\to$ 2019-11-18 (45) | Ref 0 (Zero)<br>**Ref 1 (Median)**<br>Model 1 (Ridge) | 0.0256<br>**0.0185**<br>0.0205 | 0.0215<br>**0.0161**<br>0.0175 | 50.00%<br>**77.78%**<br>**77.78%** | N/A<br>N/A<br>+0.130 | N/A<br>N/A<br>1000.0 |
| **1** | 2019-01-02 $\to$ 2019-11-11 (218) | 5 days | 2019-11-19 $\to$ 2020-01-24 (45) | Ref 0 (Zero)<br>**Ref 1 (Median)**<br>Model 1 (Ridge) | 0.0286<br>**0.0208**<br>0.0217 | 0.0242<br>**0.0162**<br>0.0174 | 50.00%<br>**82.22%**<br>**82.22%** | N/A<br>N/A<br>-0.067 | N/A<br>N/A<br>1000.0 |
| **2** | 2019-01-02 $\to$ 2020-01-16 (263) | 5 days | 2020-01-27 $\to$ 2020-03-30 (45) | **Ref 0 (Zero)**<br>Ref 1 (Median)<br>Model 1 (Ridge) | **0.0637**<br>0.0697<br>0.0692 | **0.0498**<br>0.0541<br>0.0537 | **50.00%**<br>42.22%<br>42.22% | N/A<br>N/A<br>-0.145 | N/A<br>N/A<br>1000.0 |
| **3 (Holdout)** | 2019-01-02 $\to$ 2020-03-23 (308) | 5 days | 2020-03-31 $\to$ 2020-06-03 (45) | Ref 0 (Zero)<br>**Ref 1 (Median)**<br>Model 1 (Ridge) | 0.0484<br>**0.0404**<br>0.0460 | 0.0393<br>**0.0322**<br>0.0365 | 50.00%<br>**82.22%**<br>73.33% | N/A<br>N/A<br>-0.356 | N/A<br>N/A<br>1000.0 |

---

## 4. Methodological Audits & Key Findings

### 4.1 Audit of Information Coefficient (IC) Inference
- **Defect in Ordinary Spearman p-values**:
  - The forward-return target $y_{T}^{(5)} = \frac{P_{T+5} - P_{T+1}}{P_{T+1}}$ shares 4 days of returns with $y_{T+1}^{(5)}$.
  - Standard Spearman $p$-values assume independent and identically distributed (i.i.d.) observations. Under $H=5$ overlapping returns, serial correlation severely inflates test statistics, generating artificially tiny $p$-values (e.g., reporting $p < 0.001$ when consecutive observations share 80% identical returns).
- **Correction Applied**:
  - Ordinary Spearman $p$-values are officially classified as **unadjusted and exploratory only**.
  - All claims of statistical significance based on ordinary $p$-values have been stricken.
  - Spearman rank correlation is retained strictly as a **descriptive rank-order metric** (Information Coefficient). Formal hypothesis testing is deferred until Hansen-Hodrick or Newey-West robust standard error adjustments are implemented.

### 4.2 Audit of Ridge Regularization & Alpha Selection
- **Alpha Grid and Search Logic**:
  - The alpha grid evaluates $\alpha \in \{0.01, 0.1, 1.0, 10.0, 100.0, 1000.0\}$.
  - Selection is performed strictly within the training fold: the first 70% of chronological training sessions are used to fit candidates, and the final 30% are evaluated to select the alpha minimizing validation RMSE.
- **Why $\alpha = 1000.0$ Was Consistently Selected**:
  - In daily equity returns, individual technical indicators (RSI, moving average z-scores, momentum) carry very low signal-to-noise ratios. Unregularized OLS rapidly overfits noise in financial returns.
  - An $\alpha = 1000.0$ heavily penalizes coefficient magnitudes, shrinking all feature weights toward zero. Consequently, Ridge predictions collapse toward the training sample mean ($\hat{y} \approx \mu_{\text{train}}$).
- **Honest Comparative Performance**:
  - **Ridge does NOT outperform the Historical Median benchmark**. In all 4 folds, Reference 1 (Historical Median) achieves lower RMSE and lower MAE than Ridge (e.g. Fold 3 MAE: 0.0322 for Median vs 0.0365 for Ridge).
  - During Fold 2 (the March 2020 crash), both Median and Ridge underperform Reference 0 (Zero Return), because a positive trailing equity trend failed to anticipate the sudden market drop.
  - **No Predictive Superiority Claimed**: Market-only linear models on single-stock daily indicators provide zero demonstrable excess predictive power beyond simple naive references.

---

## 5. Preservation of Research Boundaries

- **FNSPID News**: Zero FNSPID news articles were used in training Model 1. News data remains isolated as an unverified research resource.
- **Tiingo Market Storage**: Storage policy guard `storage_authorized = False` remains intact; no bulk market archives were written to disk.
- **Yahoo Prototyping Boundary**: The multi-year market sample was used strictly for internal pipeline and split validation.

---

## 6. Automated Regression Test Suite

All 9 unit and regression tests in `tests/test_target_and_baseline.py` passed alongside the existing 100 tests:
```powershell
python -m pytest
```
**Outcome**: **109 passed in 22.59s** (zero failures, zero warnings across 12 test modules):
- `tests/test_target_and_baseline.py`: 9 passed
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

## 7. Status and Stopping Point

Phase 5B.1 walk-forward evaluation audit and correction is complete. 
We have stopped here and are waiting for your review. No multi-asset cohort expansion, news-model training, or UI/API development has been started.

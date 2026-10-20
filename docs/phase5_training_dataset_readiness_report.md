# Phase 5A — Training Data Readiness Verification and Contract Finalization Report

**Date:** 2026-10-16  
**Status:** Verification Complete — Conditional Go / Staged Roadmap Defined  
**Governing Modules:** `src/data/market/storage_policy.py`, `src/features/dataset.py`, `src/features/alignment.py`, `src/features/market.py`, `src/features/fundamental.py`, `src/features/news.py`

---

## 1. Data-Use Authorization Status by Source

An authoritative, evidence-backed inspection of data rights and licensing constraints establishes the legal boundary for all training activities:

| Data Source | Primary Role in Pipeline | Authoritative Terms / Legal Basis | Date Verified | Authorization Classification | Storage & Use Governance Decision |
| :--- | :--- | :--- | :---: | :---: | :--- |
| **SEC EDGAR (`data.sec.gov`)** | Primary Fundamentals & Corporate Disclosure | **17 U.S.C. § 105** (Works of US Government); EDGAR Access Disclaimers | 2026-10-16 | **PERMITTED** | **Approved for Training Artifacts**. Free public domain; persistent caching of raw JSON and normalized Parquet is explicitly permitted under SEC User-Agent throttling (10 req/s). |
| **Tiingo End-of-Day API** | Primary Multi-Year Market Quotes (2018–2024 pilot) | **Tiingo Terms of Service (Starter Tier)**: Prohibits local database persistence and bulk archiving; permits personal/internal research and non-commercial transient display. | 2026-10-16 | **RESTRICTED / UNVERIFIED for Disk Persistence**; **PERMITTED for In-Memory Features** | **Approved ONLY in In-Memory Mode**. `storage_authorized = False` strictly enforced. Transformed non-reversible mathematical features are permitted for internal research, but raw/normalized Parquet cannot be permanently written to disk or redistributed without an Enterprise license. |
| **Existing S&P 500 Market Sample (`sp500_market_sample.parquet`)** | Historical Multi-Decade Market Benchmarks (1962–2023) | **Yahoo Finance Terms of Service**: Automated scraping, persistent warehousing, and commercial redistribution are prohibited. Widely used in academic prototypes under fair use. | 2026-10-16 | **UNVERIFIED / RESTRICTED** | **Prototyping & Temporal Overlap Validation Only**. Kept strictly local for verifying historical feature pipelines. **Cannot be claimed as an authorized commercial/production training artifact.** |
| **FNSPID Financial News Sample (`fnspid_news_processed.parquet`)** | Auxiliary Pre-2020 News Benchmark | **Academic Research Dataset (Hugging Face / Zenodo)**. Raw text comprises scraped articles from commercial publishers (Benzinga, Reuters, Bloomberg) without documented publisher redistribution consent. | 2026-10-16 | **UNVERIFIED** | **Isolated from Authorized Training Datasets**. Permitted solely as an auxiliary research benchmark for evaluating the multi-modal pipeline architecture. **Must NOT be classified as an approved primary training source.** |

### Key Authorization Decision:
- **Baseline Models (Market-Only & Fundamentals)**: Will execute using **SEC EDGAR** (fully permitted) and **Tiingo market features in-memory** (or local research market samples strictly bounded for academic validation).
- **News Integration**: Treated as an **experimental research ablation**, cleanly separated from the core baseline until a copyright-unencumbered news stream (e.g., SEC Form 8-K material disclosures or licensed news feeds) is integrated.

---

## 2. Independent Validation of Empirical Overlap (Apple Inc. / `AAPL`)

We independently audited the actual local Parquet files (`data/processed/market/sp500_market_sample.parquet`, `data/processed/sec/facts/pilot_financial_facts.parquet`, `data/processed/news/fnspid_news_processed.parquet`, `data/processed/universe/sp500_universe.parquet`) and reproduced the multi-modal alignment under the Phase 4C dataset builder contract.

### 2.1 Empirical Findings on Apple Inc. (`US_CIK_0000320193`)
- **Active News Window**: `2020-03-09` to `2020-06-10` (84 calendar days).
- **Trading Sessions**: Exactly **66 valid exchange sessions** (excluding weekends and Good Friday on 2020-04-10).
- **Pairwise Market + SEC Overlap**: **100.0% (66 / 66 sessions)**.
  - Active filings available: Form 10-Q filed 2020-01-29 ($9.182 \times 10^{10}$ revenue) and Form 10-Q filed 2020-04-30 ($5.831 \times 10^{10}$ revenue).
  - All 66 sessions classified as `active_with_facts` with 0 stale fact occurrences ($\le 400$ days).
- **Pairwise Market + News Overlap**:
  - Exactly **441 articles** present for AAPL.
  - Timestamp precision: 100% (441/441) have valid intraday UTC timestamps (`has_intraday_time = True`), ranging from `2020-03-09 00:00:00 UTC` to `2020-06-10 07:33:26 UTC`.
  - **Article text limitation**: 100% of rows contain **headlines only** (`article_text` length = 0). NLP features must rely on headline text or statistical count/recency indicators.
  - **Daily Activity**: 61 of 66 sessions (92.4%) have $\ge 1$ article in the trailing 24 hours. Under 3-day and 7-day lookback windows, trailing event coverage reaches 64 (97.0%) and 66 (100.0%) sessions.
  - All 66 sessions classified as `active_with_events` when trailing lookback is evaluated.
- **Warm-Up Period Precondition**:
  - Indicators with long lookbacks (e.g., 200-day SMA, 63-day volatility) require a warm-up period. When market history is provided starting from `2019-01-01`, **100% of market features (0 nulls) are populated across the entire 66-session evaluation window**.

---

## 3. Forward-Return Target Specification & Price Conventions

To eliminate execution lookahead leakage while providing a robust prediction target, the forward-return target is formally specified:

### 3.1 Mathematical Definition: Feasible 5-Trading-Session Forward Return
For a decision formulated at session $T$ market close ($T_{\text{close}}$, 16:00 ET):
- **Executable Entry**: Session $T+1$ opening auction ($T+1_{\text{open}}$, 09:30 ET).
- **Executable Exit**: Session $T+5$ market close ($T+5_{\text{close}}$, 16:00 ET).
- **Forward Return Target ($y_{T}^{(5)}$)**:
  $$y_{T}^{(5)} = \frac{P_{T+5, \text{close}}^{\text{adj}} - P_{T+1, \text{open}}^{\text{adj}}}{P_{T+1, \text{open}}^{\text{adj}}}$$

### 3.2 Price & Corporate Action Invariants
1. **Total Return via Split/Dividend Adjusted Prices**:
   - Raw prices ($P$) undergo discontinuous step changes on ex-dividend and split dates (e.g., Apple's 4-for-1 split on 2020-08-31 dropped raw price from ~$500 to ~$125).
   - The label calculation **MUST** use split- and dividend-adjusted prices ($P^{\text{adj}}$) to represent true total economic return.
   - For datasets where only `open`, `close`, and `adjusted_close` exist (such as `sp500_market_sample`), adjusted open is constructed via the split adjustment ratio:
     $$P_{t, \text{open}}^{\text{adj}} = P_{t, \text{open}} \times \left(\frac{P_{t, \text{close}}^{\text{adj}}}{P_{t, \text{close}}}\right)$$
   - In Tiingo data, `adjusted_open` is directly provided as a first-class verified field.
2. **Exclusion of Terminal Horizon Rows**:
   - For a dataset ending on session $N$, rows $N-4, N-3, N-2, N-1, N$ have unavailable future exit prices ($T+5 > N$).
   - These final 5 rows are retained for feature inference but **MUST be excluded from training and validation loss calculations**.
3. **Overlapping Labels**:
   - Because $y_{T}^{(5)}$ and $y_{T+1}^{(5)}$ share 4 trading sessions, their target returns are serially correlated. This does not bias point predictions under OLS/Ridge, but standard error estimates and standard k-fold cross-validation are invalidated.

---

## 4. Chronological Walk-Forward Evaluation Contract

To prevent lookahead leakage and data snooping, the evaluation contract enforces the following strict rules:

### 4.1 Temporal Cross-Validation Structure
- **Strictly Chronological Splits**: Random shuffling and standard k-fold splitting are strictly prohibited.
- **Walk-Forward Expanding or Rolling Folds**:
  ```
  Fold 1:  [ Train: T_0 -> T_k ] ── Purge (5 days) ── [ Val: T_{k+6} -> T_{k+m} ]
  Fold 2:  [ Train: T_0 -> T_{k+m} ] ── Purge (5 days) ── [ Val: T_{k+m+6} -> T_{k+2m} ]
  Final:   [ Train + Val ] ──────── Purge (5 days) ── [ Out-of-Sample Test ]
  ```
- **Purging & Embargoing**:
  - A **5-session purge window** is enforced between the end of the training set and the start of the validation set to eliminate overlapping forward-return target contamination ($T_{\text{train, last}} + 5 < T_{\text{val, first}}$).
  - An **embargo window** is added to prevent auto-regressive feature leakage.

### 4.2 Data Transformation Preconditions
- **Leakage-Free Preprocessing**:
  - Feature scalers (`StandardScaler`, `RobustScaler`), mean/median imputers, and PCA transformations **MUST be fit strictly on the training fold**.
  - Validation and test folds are transformed using parameters learned exclusively from the training fold.
- **Model Selection Separation**:
  - Hyperparameter tuning (e.g., Ridge $\alpha$, LightGBM tree depth) is conducted strictly on validation splits.
  - The held-out test split is evaluated exactly once on the selected model configuration.

### 4.3 Baseline Model Hierarchy & Naive References
1. **Reference 0 (Zero Return Naive)**: Assumes $\hat{y} = 0.0$.
2. **Reference 1 (Historical Median Return Naive)**: Assumes $\hat{y} = \text{median}(y_{\text{train}})$.
3. **Model 1 (Market-Only Ridge / ElasticNet)**: Linear model with L1/L2 shrinkage on standardized market technical indicators (returns, volatility, RSI, volume ratios).
4. **Evaluation Metrics**:
   - **Root Mean Squared Error (RMSE)**
   - **Mean Absolute Error (MAE)**
   - **Directional Accuracy (Hit Rate)**: $\text{sign}(\hat{y}) == \text{sign}(y)$
   - **Information Coefficient (IC)**: Spearman rank correlation between $\hat{y}$ and $y$.

---

## 5. Unresolved Blockers & Limitations

1. **FNSPID News Licensing (`UNVERIFIED`)**:
   - Commercial web-scraped article provenance precludes deploying FNSPID into an authorized production training artifact.
   - *Mitigation*: Restrict initial baseline development to Market + SEC Fundamentals (both fully verified), treating FNSPID as an experimental ablation study only.
2. **Market Persistent Storage Authorization (`storage_authorized = False`)**:
   - Tiingo Starter terms prevent saving raw/normalized Parquet databases to disk.
   - *Mitigation*: Continue utilizing the pipeline's verified in-memory processing (`persistence_mode = IN_MEMORY`). Datasets and features are assembled dynamically during the training run.
3. **Short News Overlap Window (March–June 2020)**:
   - 66 sessions represent an effective proof-of-concept for multi-modal alignment, but are insufficient for long-term out-of-sample statistical significance.
   - *Mitigation*: Long-horizon training (e.g., 2018–2023) will rely on the Market + SEC Fundamental pipeline, where continuous multi-year coverage is fully verified.

---

## 6. Go / No-Go Decision & Next Step

### Decision: **CONDITIONAL GO**
- **GO** for Phase 5B: Implementing the target calculation, walk-forward chronological splitter, and the **Market-Only Predictive Baseline (Model 1: Ridge Regression)**.
- **NO-GO** for claiming FNSPID as an authorized primary training artifact or persisting unverified market archives to disk.

### Smallest Next Implementation Step (Phase 5B):
1. Implement `ForwardReturnTargetEngine` (or utility) in `src/features/` to compute $y_{T}^{(5)}$ and mask terminal horizon rows.
2. Implement `WalkForwardSplitter` with configurable purge/embargo windows.
3. Implement `MarketBaselineModel` (Ridge regression with cross-validated $\alpha$) and evaluate on AAPL over the verified historical period.
4. Add regression tests validating no lookahead in target generation and zero data leakage across walk-forward splits.

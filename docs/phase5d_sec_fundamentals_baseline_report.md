# Phase 5D — Point-in-Time SEC Fundamentals Integration Report

**Date:** 2026-10-16  
**Status:** Completed & Audited — Incremental Predictive Value Empirically Evaluated  
**Artifacts Produced / Updated:**  
- `src/models/baseline.py` (`MarketBaselinePipeline` updated with `MARKET_FEATURE_COLUMNS`, `FUNDAMENTAL_FEATURE_COLUMNS`, `COMBINED_FEATURE_COLUMNS`, and configurable `model_name`)  
- `scripts/evaluate_phase5d.py` (Reproducible 4-fold walk-forward comparative experiment script)  
- `tests/test_target_and_baseline.py` (`TestFundamentalPointInTimeAndBaseline` regression suite with 4 new tests; 117 total passing tests across 12 modules)  
- `docs/phase5d_sec_fundamentals_baseline_report.md` (This document)

---

## 1. Executive Summary & Objective

In **Phase 5D**, we integrated historical point-in-time SEC EDGAR financial fundamentals into the existing predictive pipeline. We designed a controlled, chronological walk-forward experiment to evaluate whether point-in-time accounting fundamentals and financial health ratios provide incremental predictive power for forecasting five-trading-session forward returns ($y_T^{(5)}$) beyond market-only technical indicators and simple baselines.

### Primary Empirical Findings:
1. **No Consistent Incremental Predictive Value**: In the 4-company panel (`AAPL`, `JPM`, `GOOG`, `TSLA`), adding SEC fundamental features produced marginal MAE reductions in Folds 0 & 1, but offered zero downside protection during the March 2020 COVID crash (Fold 2) and degraded out-of-sample performance in the chronological holdout period (Fold 3, MAE 0.0504 vs 0.0497; IC degraded from $-0.155$ to $-0.200$).
2. **Simple Baselines Dominate or Match Regularized Linear Models**: Across both the 4-company panel and the complete-fundamentals 2-company cohort (`AAPL` + `JPM`), the simple **Historical Median** baseline outperformed or matched the Market-Plus-Fundamentals Ridge model in 3 of 4 folds on MAE. In the March 2020 crash fold, the **Zero-Return** benchmark was superior to all models.
3. **Data Availability Reality**: In the local SEC pilot dataset (`pilot_financial_facts.parquet`), historical financial facts exist for `AAPL`, `JPM`, `MSFT`, `FB/META`, and `CELG`. Of the Phase 5C market evaluation cohort, only `AAPL` and `JPM` have local SEC fundamental facts; `GOOG` and `TSLA` have missing fundamentals (`fundamental_coverage_status = "source_unavailable"`). Imputation strictly on training folds preserved leak-free execution, but fundamentals for non-covered assets act as uninformative training constants.
4. **Recommendation**: We issue a **CONDITIONAL GO / REJECT CLAIMS OF FUNDAMENTAL ALPHA**. Fundamental features must remain optional. The system must not claim that quarterly accounting fundamentals improve short-horizon (5-session) price return predictions.

---

## 2. Task 1: Audit of Existing SEC Data & Ingestion

We conducted a read-only audit of the existing SEC data files in `data/processed/sec/facts/pilot_financial_facts.parquet` and the raw filings in `data/raw/sec/companyfacts/`.

### 2.1 File Inventory & Properties
- **Processed Parquet**: `data/processed/sec/facts/pilot_financial_facts.parquet`
- **Total Facts**: 9,229 rows $\times$ 17 columns
- **Schema Columns**: `company_id`, `entity_name`, `cik`, `taxonomy`, `concept`, `unit`, `period_end`, `period_type`, `value`, `accession_number`, `form`, `filing_date`, `acceptance_timestamp`, `fy`, `fp`, `is_amendment`, `amendment_flag`
- **Nulls**: Exactly **0** nulls in `company_id`, `cik`, `concept`, `value`, `acceptance_timestamp`, `accession_number`, or `form`.
- **Duplicate Facts**: Exactly **0** unhandled duplicate records for identical `(company_id, concept, period_end, accession_number)`.

### 2.2 Coverage Comparison: Pilot Entities vs Phase 5C Evaluation Cohort

| Entity Ticker | Canonical Company ID | SEC CIK | In Pilot Facts Parquet? | Fact Count | Earliest Filing Acceptance | Latest Filing Acceptance | Filing Forms Present | Evaluated in Phase 5C Market Baseline? | SEC Coverage Status in 5D Panel |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **AAPL** | `US_CIK_0000320193` | `0000320193` | **YES** | 2,381 | 2008-11-05 | 2024-02-02 | 10-K, 10-Q, 10-K/A, 10-Q/A | YES | `active_with_facts` (100% fresh) |
| **JPM** | `US_CIK_0000019617` | `0000019617` | **YES** | 1,278 | 2009-02-27 | 2024-02-16 | 10-K, 10-Q, 10-K/A | YES | `active_with_facts` (100% fresh) |
| **MSFT** | `US_CIK_0000789019` | `0000789019` | **YES** | 2,341 | 2009-07-30 | 2024-01-30 | 10-K, 10-Q, 10-Q/A | NO (Not in market sample) | N/A |
| **FB / META** | `US_CIK_0001326801` | `0001326801` | **YES** | 1,784 | 2012-07-31 | 2024-02-02 | 10-K, 10-Q | NO (Not in market sample) | N/A |
| **CELG** | `US_CIK_0000816284` | `0000816284` | **YES** | 1,445 | 2009-02-17 | 2019-11-07 | 10-K, 10-Q | NO (Acquired by BMY 2019) | N/A |
| **GOOG** | `US_CIK_0001652044` | `0001652044` | **NO** | 0 | N/A | N/A | None | YES | `source_unavailable` (0 facts) |
| **TSLA** | `US_CIK_0001318605` | `0001318605` | **NO** | 0 | N/A | N/A | None | YES | `source_unavailable` (0 facts) |

### 2.3 Semantic Accounting Differences (Commercial vs Financial Firms)
- **Classified Balance Sheets vs Banking Financial Statements**: Commercial entities like Apple report `AssetsCurrent` and `LiabilitiesCurrent`, enabling calculation of `fundamental_ratio_current_ratio`. Commercial entities also report `OperatingIncomeLoss`.
- In contrast, bank holding companies like JPMorgan Chase (`JPM`) report unclassified balance sheets and banking income statements (`InterestAndDividendIncomeOperating`, `NoninterestIncome`, etc.). Consequently, for JPM, `fundamental_operating_income` and `fundamental_ratio_current_ratio` are not reported and evaluate to `NaN`. The pipeline preserves these as missing rather than fabricating zeroes.

---

## 3. Tasks 2 & 3: Point-in-Time Fundamental Features, Amendments & Integrity

### 3.1 Point-in-Time Availability Boundary
For any historical decision at timestamp $T_{\text{decision}}$, information availability is governed strictly by the SEC EDGAR filing acceptance timestamp:
$$\text{Filing is Available at } T_{\text{decision}} \iff T_{\text{acceptance}} \le T_{\text{decision}}$$
The fiscal period end date ($T_{\text{period\_end}}$) is explicitly **not** used as the availability boundary. For example, Apple's Q1 fiscal period ending on December 28, 2019 was accepted on EDGAR on January 29, 2020 at 16:30:12 EST. Any decision point on or prior to January 29, 2020 before acceptance can only see the prior Q4 filing from October 31, 2019.

### 3.2 Amendment & Restatement Handling
When a company files an amended filing (e.g. 10-K/A or 10-Q/A) that restates a previously reported fact:
1. Prior to the amendment's EDGAR acceptance timestamp, the original fact remains authoritative and is returned in snapshots.
2. After the amendment's EDGAR acceptance timestamp, the amendment supersedes the original value for that period.
3. Accession numbers (`fundamental_<concept>_accn`) and filing forms (`fundamental_<concept>_form`) are tracked per feature to guarantee complete audit provenance.

### 3.3 Concept Definitions & Formulas

| Feature Column | Source Concept(s) (US-GAAP XBRL) | Formula / Definition | Unit / Scale |
| :--- | :--- | :--- | :---: |
| `fundamental_revenue` | `Revenues`, `RevenueFromContractWithCustomerExcludingAssessedTax`, `SalesRevenueNet` | Reported total top-line revenue for duration period | USD |
| `fundamental_net_income` | `NetIncomeLoss`, `ProfitLoss` | Reported net income (loss) for duration period | USD |
| `fundamental_total_assets` | `Assets` | Total consolidated assets at instant period end | USD |
| `fundamental_total_liabilities` | `Liabilities` | Total liabilities at instant period end | USD |
| `fundamental_stockholders_equity`| `StockholdersEquity` | Total stockholders' equity at instant period end | USD |
| `fundamental_operating_cash_flow`| `NetCashProvidedByUsedInOperatingActivities` | Operating cash flow for duration period | USD |
| `fundamental_diluted_eps` | `EarningsPerShareDiluted` | Diluted earnings per share | USD/share |
| `fundamental_ratio_net_margin` | Net Income / Revenue | `net_income / revenue` (safe div, requires revenue > 0) | Dimensionless |
| `fundamental_ratio_roa` | Net Income / Assets | `net_income / total_assets` | Dimensionless |
| `fundamental_ratio_debt_to_assets`| Liabilities / Assets | `total_liabilities / total_assets` | Dimensionless |
| `fundamental_ratio_debt_to_equity`| Liabilities / Equity | `total_liabilities / stockholders_equity` | Dimensionless |
| `fundamental_ratio_ocf_to_net_income`| Operating Cash Flow / Net Income | `operating_cash_flow / net_income` | Dimensionless |
| `fundamental_revenue_age_days` | Period End Date to Decision Date | Calendar days since filing period end | Integer Days |
| `fundamental_all_facts_stale` | Staleness Threshold | Boolean flag if facts exceed configured max age (400 days) | Binary (0/1) |

---

## 4. Task 4: Unified Dataset Integration

Using `UnifiedDatasetBuilder(DatasetBuildConfig(market_config=MarketFeatureConfig(decision_timing=DecisionTimingMode.NEXT_SESSION_OPEN), pre_open_cutoff_minutes=15))`, market features and SEC fundamentals were merged on `(company_id, decision_timestamp)`.

### 4.1 Invariants Maintained
- **Unique Rows**: Exactly 1,452 total panel rows (363 dates $\times$ 4 companies).
- **Valid Labeled Rows**: Exactly 1,432 rows (358 dates $\times$ 4 companies) with 5 terminal sessions per company masked.
- **Coverage Status**:
  - `AAPL`: 358 valid rows with `fundamental_coverage_status = "active_with_facts"` (100% fresh, 0 stale).
  - `JPM`: 358 valid rows with `fundamental_coverage_status = "active_with_facts"` (100% fresh, 0 stale).
  - `GOOG`: 358 valid rows with `fundamental_coverage_status = "source_unavailable"`.
  - `TSLA`: 358 valid rows with `fundamental_coverage_status = "source_unavailable"`.
- **Zero Fabrication**: Unavailable fundamentals for `GOOG` and `TSLA` remain strictly `NaN` in raw feature output.

---

## 5. Task 5: Fair Comparative Experiment

We executed two comparative evaluations across all 4 chronological walk-forward folds:
1. **Experiment 1: Full Four-Company Panel** (`AAPL`, `JPM`, `GOOG`, `TSLA` — 1,432 rows, 358 dates).
2. **Experiment 2: Two-Company Complete-Fundamentals Cohort** (`AAPL`, `JPM` — 716 rows, 358 dates).

### 5.1 Protocol & Strict Temporal Controls
- **Target**: 5-session forward return $y_T^{(5)} = (P_{T+5,\text{close}}^{\text{adj}} - P_{T+1,\text{open}}^{\text{adj}}) / P_{T+1,\text{open}}^{\text{adj}}$.
- **Purge Gap**: Exactly 5 complete calendar trading dates (20 panel rows in Exp 1, 10 panel rows in Exp 2) purged between training end and validation start.
- **Zero Lookahead**: The last training target exit date is strictly prior to the first validation decision date.
- **Preprocessing Isolation**: `SimpleImputer(strategy="median")` and `StandardScaler()` fit strictly on training fold data.
- **Hyperparameter Grid**: Ridge regularizer $\alpha \in \{0.01, 0.1, 1.0, 10.0, 100.0, 1000.0\}$ tuned on train splits.
- **Models Evaluated**:
  - **Reference 0**: Naive Zero Return ($y_{\text{pred}} = 0$).
  - **Reference 1**: Historical Median Return ($y_{\text{pred}} = \text{median}(y_{\text{train}})$).
  - **Model 1**: Market-Only Ridge Baseline (17 technical market features from Phase 5C).
  - **Model 2**: Market + Fundamentals Ridge Baseline (17 market features + 8 fundamental features).

---

### 5.2 Experiment 1: Four-Company Panel Detailed Results

#### Fold 0 (Train: `2019-01-02` $\to$ `2019-09-09` [692 rows] | Purge: 5 dates | Val: `2019-09-17` $\to$ `2019-11-18` [180 rows])
- **Selected Ridge $\alpha$**: Market `1000.0` | Mkt+Fund `1000.0`
- **Descriptive IC**: Market `-0.101` | Mkt+Fund `-0.023`

| Model / Baseline | Aggregate RMSE | Aggregate MAE | Aggregate Hit Rate | AAPL MAE (Hit) | JPM MAE (Hit) | GOOG MAE (Hit) | TSLA MAE (Hit) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Reference 0 (Zero Return)** | 0.0486 | 0.0300 | 50.00% | 0.0215 (50.0%) | 0.0210 (50.0%) | 0.0162 (50.0%) | 0.0613 (50.0%) |
| **Reference 1 (Historical Median)** | **0.0464** | **0.0277** | **70.56%** | **0.0180 (77.8%)** | **0.0194 (66.7%)** | **0.0144 (71.1%)** | **0.0589 (66.7%)** |
| **Model 1 (Market-Only Ridge)** | 0.0485 | 0.0295 | 62.78% | 0.0200 (75.6%) | 0.0201 (64.4%) | 0.0151 (68.9%) | 0.0626 (42.2%) |
| **Model 2 (Market + Fundamentals)**| 0.0484 | 0.0291 | 61.11% | **0.0175 (77.8%)** | 0.0205 (57.8%) | 0.0151 (68.9%) | 0.0632 (40.0%) |

#### Fold 1 (Train: `2019-01-02` $\to$ `2019-11-11` [872 rows] | Purge: 5 dates | Val: `2019-11-19` $\to$ `2020-01-24` [180 rows])
- **Selected Ridge $\alpha$**: Market `1000.0` | Mkt+Fund `1000.0`
- **Descriptive IC**: Market `+0.304` | Mkt+Fund `+0.284`

| Model / Baseline | Aggregate RMSE | Aggregate MAE | Aggregate Hit Rate | AAPL MAE (Hit) | JPM MAE (Hit) | GOOG MAE (Hit) | TSLA MAE (Hit) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Reference 0 (Zero Return)** | 0.0481 | 0.0317 | 50.00% | 0.0242 (50.0%) | **0.0134 (50.0%)** | 0.0192 (50.0%) | 0.0701 (50.0%) |
| **Reference 1 (Historical Median)** | 0.0445 | 0.0289 | **72.22%** | 0.0190 (82.2%) | 0.0139 (53.3%) | **0.0176 (68.9%)** | 0.0650 (84.4%) |
| **Model 1 (Market-Only Ridge)** | **0.0426** | 0.0281 | **72.22%** | 0.0195 (82.2%) | 0.0136 (53.3%) | 0.0178 (68.9%) | **0.0615 (84.4%)** |
| **Model 2 (Market + Fundamentals)**| 0.0428 | **0.0276** | **72.22%** | **0.0163 (82.2%)** | 0.0138 (53.3%) | 0.0179 (68.9%) | 0.0624 (84.4%) |

#### Fold 2 (Train: `2019-01-02` $\to$ `2020-01-16` [1052 rows] | Purge: 5 dates | Val: `2020-01-27` $\to$ `2020-03-30` [180 rows, COVID Crash])
- **Selected Ridge $\alpha$**: Market `1000.0` | Mkt+Fund `1000.0`
- **Descriptive IC**: Market `-0.080` | Mkt+Fund `-0.095`

| Model / Baseline | Aggregate RMSE | Aggregate MAE | Aggregate Hit Rate | AAPL MAE (Hit) | JPM MAE (Hit) | GOOG MAE (Hit) | TSLA MAE (Hit) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Reference 0 (Zero Return)** | **0.1170** | **0.0796** | **50.00%** | **0.0498 (50.0%)** | **0.0640 (50.0%)** | **0.0435 (50.0%)** | **0.1611 (50.0%)** |
| **Reference 1 (Historical Median)** | 0.1189 | 0.0819 | 42.78% | 0.0520 (42.2%) | 0.0680 (35.6%) | 0.0448 (48.9%) | 0.1626 (44.4%) |
| **Model 1 (Market-Only Ridge)** | 0.1208 | 0.0827 | **44.44%** | 0.0516 (42.2%) | 0.0654 (44.4%) | 0.0439 (46.7%) | 0.1699 (44.4%) |
| **Model 2 (Market + Fundamentals)**| 0.1207 | 0.0827 | 43.89% | 0.0516 (44.4%) | 0.0658 (42.2%) | 0.0438 (46.7%) | 0.1695 (42.2%) |

#### Fold 3 (Holdout) (Train: `2019-01-02` $\to$ `2020-03-23` [1232 rows] | Purge: 5 dates | Val: `2020-03-31` $\to$ `2020-06-03` [180 rows, Rebound])
- **Selected Ridge $\alpha$**: Market `1000.0` | Mkt+Fund `1000.0`
- **Descriptive IC**: Market `-0.155` | Mkt+Fund `-0.200`

| Model / Baseline | Aggregate RMSE | Aggregate MAE | Aggregate Hit Rate | AAPL MAE (Hit) | JPM MAE (Hit) | GOOG MAE (Hit) | TSLA MAE (Hit) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Reference 0 (Zero Return)** | 0.0773 | 0.0536 | 50.00% | 0.0393 (50.0%) | 0.0619 (50.0%) | 0.0290 (50.0%) | 0.0842 (50.0%) |
| **Reference 1 (Historical Median)** | 0.0738 | 0.0502 | **72.78%** | 0.0347 (82.2%) | **0.0606 (60.0%)** | **0.0251 (75.6%)** | 0.0806 (73.3%) |
| **Model 1 (Market-Only Ridge)** | **0.0732** | **0.0497** | 70.00% | 0.0332 (82.2%) | **0.0606 (60.0%)** | 0.0265 (64.4%) | **0.0786 (73.3%)** |
| **Model 2 (Market + Fundamentals)**| 0.0740 | 0.0504 | 67.22% | **0.0331 (82.2%)** | 0.0632 (48.9%) | 0.0265 (64.4%) | 0.0787 (73.3%) |

---

### 5.3 Experiment 2: Two-Company Complete-Fundamentals Cohort (`AAPL` + `JPM`)

To address the missingness of GOOG and TSLA fundamentals directly, we repeated the 4-fold walk-forward evaluation strictly on the subset of companies with 100% complete point-in-time SEC fundamentals.

| Fold | Dates / Regime | Ref 0 (Zero) MAE | Ref 1 (Median) MAE | Model 1 (Market) MAE | Model 2 (Mkt+Fund) MAE | Model 1 IC | Model 2 IC | Winner on MAE |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Fold 0** | 2019-09-17 $\to$ 2019-11-18 | 0.0212 | **0.0184** | 0.0200 | 0.0186 | +0.215 | +0.280 | **Ref 1 (Median)** |
| **Fold 1** | 2019-11-19 $\to$ 2020-01-24 | 0.0188 | 0.0162 | 0.0169 | **0.0161** | +0.194 | +0.282 | **Model 2 (Mkt+Fund)** |
| **Fold 2** | 2020-01-27 $\to$ 2020-03-30 (Crash) | **0.0569** | 0.0605 | 0.0622 | 0.0614 | +0.149 | +0.053 | **Ref 0 (Zero Return)** |
| **Fold 3** | 2020-03-31 $\to$ 2020-06-03 (Holdout) | 0.0506 | **0.0475** | 0.0505 | 0.0582 | -0.218 | -0.275 | **Ref 1 (Median)** |

---

## 6. Critical Findings & Honest Comparative Insights

1. **Fundamentals Do Not Provide General or Consistent Incremental Value**:
   - In the 4-company panel, Model 2 improves MAE over Model 1 by at most $0.0005$ in calm bull regimes (Fold 1: 0.0276 vs 0.0281), but degrades in the untouched chronological holdout (Fold 3: 0.0504 vs 0.0497).
   - In the 2-company complete-fundamentals cohort, Model 2 noticeably degrades in Fold 3 (MAE 0.0582 vs 0.0505, RMSE 0.0752 vs 0.0648). JPM performance specifically suffered during the post-crash bank credit uncertainty (JPM MAE increased from 0.0676 to 0.0769).
2. **Frequency Mismatch Explains the Lack of Incremental Value**:
   - Fundamental financial statements are reported **quarterly** (every 90 days), while our prediction target is a **5-trading-session (weekly)** forward return.
   - For 85+ consecutive trading sessions, fundamental ratios remain static (step-functions). Short-term market dynamics and systematic liquidity shocks (such as the March 2020 COVID crash) completely dominate weekly returns, rendering stale quarterly accounting ratios uninformative or counter-cyclical.
3. **Cross-Sectional Rank Correlation (IC) Remains Negative or Zero in Holdouts**:
   - In Fold 3 of both experiments, Spearman rank IC is negative ($-0.200$ in Exp 1; $-0.275$ in Exp 2).
   - This proves that ranking stocks by higher historical ROA or profit margins does not reliably translate into higher 5-day forward price returns.
4. **Zero Lookahead Bias Verified**:
   - The test suite verified that post-cutoff filing acceptances cannot enter decision snapshots.
   - Restatements and amended filings are incorporated strictly on or after the amendment's acceptance timestamp.

---

## 7. Storage Governance & License Conformance

- **Data Sources**: Official SEC EDGAR public XBRL facts (`pilot_financial_facts.parquet`) and Yahoo-derived prototype market quotes (`sp500_market_sample.parquet`).
- **SEC Fair-Access**: Complies with SEC requirements (declarative User-Agent; 10 req/s rate limits supported by `SECFetcher`).
- **No Unlicensed Storage**: No paid APIs, external cloud databases, or unauthorized disk writes were introduced.
- **In-Memory Default**: Pipeline runs in-memory without persistent artifact caching unless explicitly configured.

---

## 8. Conclusion & Sign-Off Recommendation

| Assessment Dimension | Rating | Description |
| :--- | :---: | :--- |
| **Point-in-Time Correctness** | **PASSED (100%)** | Strict EDGAR acceptance timestamp cutoff enforced; zero future restatement leakage. |
| **Evaluation Integrity** | **PASSED (100%)** | 4-fold walk-forward splitting with 5-session purge gaps; train-only preprocessing isolation. |
| **Incremental Predictive Alpha** | **FAILED / NOT DEMONSTRATED** | Adding fundamentals does not consistently outperform market-only Ridge or simple median baselines. |
| **Sample Quality & Coverage** | **QUALIFIED** | Verified local SEC facts for AAPL and JPM; GOOG and TSLA fundamentals are unobserved in the local pilot. |

### Final Decision: CONDITIONAL GO (RESEARCH PIPELINE ACCEPTED / NO PREDICTIVE CLAIMS)
- The technical integration of SEC point-in-time fundamentals is sound, verified by regression tests, and fully operational.
- However, conforming strictly to Mandatory Constraint 6 ("Do not claim that fundamentals improve prediction unless the evaluation results demonstrate it"), **we conclude that SEC fundamentals do not provide demonstrable incremental alpha over a 5-day horizon**.
- The market-only pipeline and simple median baseline must remain the primary benchmarks. Fundamental features should remain optional.

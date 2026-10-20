# Phase 5F.1 — Final Reproducibility and Acceptance Audit Report

**Phase**: 5F.1  
**Audit Scope**: Final Reproducibility, Timestamp Provenance, and Acceptance Audit of Phase 5F  
**Date**: October 2026  
**Auditor**: Antigravity AI Agent  
**Recommendation**: **ACCEPT WITH DOCUMENTED LIMITATIONS**  

---

## 1. Objective and Audit Scope

The objective of Phase 5F.1 is to conduct a rigorous, narrowly scoped reproducibility and acceptance audit of Phase 5F before formal acceptance. This audit inspects:
1. Exact reproducibility of the walk-forward model comparison artifact [`phase5f_model_comparison_results.json`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/data/processed/sec/eight_k/phase5f_model_comparison_results.json) against [`docs/phase5f_implementation_report.md`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/docs/phase5f_implementation_report.md).
2. Traceable provenance of all 109 SEC Form 8-K acceptance timestamps back to authoritative EDGAR submission source files.
3. Strict enforcement of point-in-time dissemination buffer boundaries (09:15 ET pre-open cutoff, 5-minute buffer, timezone transitions).
4. Cross-artifact consistency between coverage JSON audits, parquet event tables, and dataset builder outputs.
5. Critical verification of model-comparison conclusions, sample alignment, and absence of trading profitability claims.
6. Execution of the complete automated regression test suite.

---

## 2. Checks Performed and Files Inspected

The following code files, configuration files, and processed artifacts were audited:

| Component | Path | Inspection Objective |
|---|---|---|
| **Evaluation Script** | [`scripts/evaluate_phase5f.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/scripts/evaluate_phase5f.py) | Walk-forward split generation, model training, evaluation pipeline, prediction pooling. |
| **Model Comparison Artifact** | [`data/processed/sec/eight_k/phase5f_model_comparison_results.json`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/data/processed/sec/eight_k/phase5f_model_comparison_results.json) | Saved fold-level and aggregate metrics across Variants A–F. |
| **Event Dataset Artifact** | [`data/processed/sec/eight_k/phase5f_8k_events.parquet`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/data/processed/sec/eight_k/phase5f_8k_events.parquet) | 109 historical Form 8-K records, schemas, and timestamps. |
| **Coverage Audit Artifact** | [`data/processed/sec/eight_k/phase5f_coverage_audit.json`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/data/processed/sec/eight_k/phase5f_coverage_audit.json) | Company-level filing counts, item classifications, and session coverage. |
| **Raw SEC Submissions** | `data/raw/sec/submissions/*.json` | Authoritative SEC EDGAR submission files (48,333 raw filings inspected). |
| **Event Ingestion Engine** | [`src/data/sec/ingestor.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/data/sec/ingestor.py) | `SECEventExtractor` logic, accession deduplication, item parsing. |
| **Event Feature Engine** | [`src/features/event.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/features/event.py) | Point-in-time eligibility checks, 5-minute buffer enforcement, snapshot logic. |
| **Baseline Model Pipeline** | [`src/models/baseline.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/models/baseline.py) | Cross-validation date grouping, isolated preprocessing during alpha tuning. |
| **Phase 5F Report** | [`docs/phase5f_implementation_report.md`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/docs/phase5f_implementation_report.md) | Reported metrics, conclusions, and limitations. |
| **Test Suites** | `tests/test_sec_events.py`, `tests/test_temporal_validation_audit.py`, full suite | Unit and regression test coverage. |

---

## 3. Model Comparison Reproducibility Audit

### 3.1 Regeneration and Numerical Fidelity
The evaluation was executed directly via `python -m scripts.evaluate_phase5f`. The regenerated metrics were compared against `phase5f_model_comparison_results.json` and `docs/phase5f_implementation_report.md`.

**Comparison Summary**:
- **Discrepancies Found**: Exactly **0 discrepancies**. The regenerated metrics reproduce the implementation report bit-for-bit across all 4 folds and aggregate totals.

| Variant | Reported RMSE | Regenerated RMSE | Reported MAE | Regenerated MAE | Reported Hit Rate | Regenerated Hit Rate | Reported IC | Regenerated IC | Status |
|---|---|---|---|---|---|---|---|---|---|
| **A (Zero Return)** | 0.0780 | 0.078007 | 0.0487 | 0.048731 | 50.00% | 50.00% | +0.000 | +0.000 | **Exact Match** |
| **B (Historical Median)** | 0.0770 | 0.077025 | 0.0472 | 0.047165 | 64.58% | 64.58% | -0.191 | -0.191 | **Exact Match** |
| **C (Market-Only Ridge)** | 0.0777 | 0.077655 | 0.0475 | 0.047489 | 62.36% | 62.36% | +0.060 | +0.060 | **Exact Match** |
| **D (Market+Fund Ridge)** | 0.0778 | 0.077836 | 0.0474 | 0.047431 | 61.11% | 61.11% | +0.045 | +0.045 | **Exact Match** |
| **E (Market+Events Ridge)** | 0.0772 | 0.077230 | 0.0472 | 0.047161 | 63.19% | 63.19% | +0.118 | +0.118 | **Exact Match** |
| **F (Market+Fund+Events)** | 0.0774 | 0.077421 | 0.0472 | 0.047173 | 60.83% | 60.83% | +0.090 | +0.090 | **Exact Match** |

### 3.2 Observation Counts and Sample Population
- **Total Scored Observations**: **720 out-of-sample observations** across the 4 outer validation folds.
- **Scored Observations per Fold**: Exactly **180 rows per fold** (45 unique trading dates $\times$ 4 companies).
  - Fold 0: 180 rows (val dates: 2019-09-17 $\rightarrow$ 2019-11-18)
  - Fold 1: 180 rows (val dates: 2019-11-19 $\rightarrow$ 2020-01-24)
  - Fold 2: 180 rows (val dates: 2020-01-27 $\rightarrow$ 2020-03-30)
  - Fold 3: 180 rows (val dates: 2020-03-31 $\rightarrow$ 2020-06-03)
- **Sample Population Identity**: **100% identical scored rows across all 6 model variants**. No model-specific missingness or sample filtering dropped any observation. Missing fundamental features and missing event features are imputed using `SimpleImputer(strategy='median')` fitted strictly on each fold's training slice.

### 3.3 Metric Aggregation Methodology
Aggregate metrics are computed by **pooling (concatenating) out-of-sample predictions and actual forward-return targets across all 4 folds ($N = 720$)**:
$$\text{MAE}_{\text{agg}} = \frac{1}{720}\sum_{i=1}^{720} |y_i - \hat{y}_i|$$
$$\text{RMSE}_{\text{agg}} = \sqrt{\frac{1}{720}\sum_{i=1}^{720} (y_i - \hat{y}_i)^2}$$
$$\text{Hit Rate}_{\text{agg}} = \frac{1}{N_{\text{valid}}}\sum_{i \in \text{valid}} \mathbb{I}(\text{sgn}(y_i) = \text{sgn}(\hat{y}_i))$$
$$\text{IC}_{\text{agg}} = \rho_{\text{Spearman}}(\mathbf{y}_{\text{OOS}}, \hat{\mathbf{y}}_{\text{OOS}})$$
Because each fold contains an equal number of trading dates (45) and observations (180), pooled aggregation weights each chronological market regime equally without fold-size distortions.

---

## 4. SEC Event Timestamp Provenance Audit

### 4.1 Traceability to Authoritative SEC Submissions
The 109 event records in `data/processed/sec/eight_k/phase5f_8k_events.parquet` were audited against all raw JSON files in `data/raw/sec/submissions/` (48,333 total raw records).

**Provenance Results**:
- **Accessions Checked**: 109 unique Form 8-K accessions.
- **Exact Raw Matches Found**: **109 of 109 (100.0%)**.
- **Mismatches / Fabrications**: **0**.
- **Inferred from `filingDate`**: **0**. Every single record extracted its timestamp directly from the authoritative SEC EDGAR `acceptanceDateTime` field.

### 4.2 Timezone and Boundary Conversion Audit
- **Timestamp Standard**: Raw EDGAR strings formatted as `YYYY-MM-DDTHH:MM:SS.000Z` are converted into timezone-aware UTC `pd.Timestamp`.
- **Daylight Saving Time Handling**: Correctly preserves UTC offsets across both Eastern Standard Time (EST, UTC-5) and Eastern Daylight Time (EDT, UTC-4).
- **Eligibility Buffer Boundary Enforcement**:
  - Decision cutoff: 09:15 ET on date $T$.
  - Buffer requirement: $T_{\text{acceptance}} + 5\text{m} \le 09:15\text{ ET}$, which strictly enforces $T_{\text{acceptance}} \le 09:10:00\text{ ET}$.
  - A filing accepted at 09:09:59 ET is eligible for date $T$.
  - A filing accepted at or after 09:10:00 ET is excluded from date $T$ and becomes eligible for date $T+1$.
  - Verified by unit tests [`tests/test_sec_events.py::test_five_minute_dissemination_buffer`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/tests/test_sec_events.py#L129-L162).
- **Critical Policy Distinction**: The 5-minute buffer is an **operational heuristic** to guard against feed ingestion delays. It does **not** constitute legal proof or a physical guarantee of public dissemination time on proprietary terminals.

---

## 5. Feature and Coverage Artifact Audit

### 5.1 Cross-Artifact Consistency
Cross-referenced [`phase5f_coverage_audit.json`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/data/processed/sec/eight_k/phase5f_coverage_audit.json), [`phase5f_8k_events.parquet`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/data/processed/sec/eight_k/phase5f_8k_events.parquet), and the generated unified dataset:

| Company | CIK | Parquet Filings | Coverage JSON Filings | Usable Timestamps | Verified Zero-Event Sessions | Sessions with Event | Unknown Sessions |
|---|---|---|---|---|---|---|---|
| **AAPL** | `0000320193` | 15 | 15 | 15 (100%) | 348 | 15 | 0 |
| **JPM** | `0000019617` | 48 | 48 | 48 (100%) | 322 | 41 | 0 |
| **GOOG** | `0001652044` | 15 | 15 | 15 (100%) | 348 | 15 | 0 |
| **TSLA** | `0001318605` | 31 | 31 | 31 (100%) | 333 | 30 | 0 |
| **Cohort** | **4 CIKs** | **109** | **109** | **109 (100%)** | **1,351 (93.04%)** | **101 (6.96%)** | **0 (0.0%)** |

All counts agree across all artifacts with zero discrepancies.

### 5.2 Preservation of Missingness Semantics
- **Verified Zero-Event Windows**: In monitored companies, calendar sessions without qualifying filings in the lookback window explicitly receive:
  - `sec_event_count_5d = 0`
  - `sec_earnings_release_in_window = 0`
  - `sec_days_since_last_8k = NaN` (or elapsed calendar days if a prior filing exists)
  - `sec_event_coverage_status = 'active'`
- **Unmonitored Companies / Unknown Coverage**: When a company is not in the monitored CIK universe, features evaluate to `NaN` with `sec_event_coverage_status = 'source_unavailable'`. No missing event data is fabricated as zero.

---

## 6. Critical Review of Model-Comparison Conclusions

### 6.1 Baseline Performance vs Event Features
- **Market-Only Ridge (Variant C)**: MAE = `0.0475` (RMSE = 0.0777, Hit = 62.36%, IC = +0.060).
- **Market-Plus-Events Ridge (Variant E)**: MAE = `0.0472` (RMSE = 0.0772, Hit = 63.19%, IC = +0.118).
- **Historical Median Baseline (Variant B)**: MAE = `0.0472` (RMSE = 0.0770, Hit = 64.58%, IC = -0.191).

### 6.2 Analysis of the Improvement Magnitude
1. **Marginal Magnitude (3 Basis Points)**: The MAE reduction from 0.0475 to 0.0472 is approximately $0.0003$ ($3$ basis points of 5-day return). This magnitude is well within standard sampling noise for a 4-company panel across 720 observations.
2. **Failure to Outperform Naive Median**: Variant E merely *matches* the MAE of the naive Historical Median baseline (`0.0472`) and has a lower directional hit rate (63.19% vs 64.58%).
3. **Cross-Asset Inconsistency**:
   - Improved error in tech equities: `AAPL` ($-0.00101$), `TSLA` ($-0.00055$), `GOOG` ($-0.00017$).
   - Degraded error in bank holding company: `JPM` ($+0.00042$ MAE, IC fell from +0.102 to +0.072).
   - High filing frequency in financial institutions (48 filings for JPM) introduced noise rather than predictive return information.
4. **No Alpha or Economic Viability**: There is **no evidence** that this model could yield positive risk-adjusted returns after bid-ask spreads, transaction costs, and slippage. Ordinary Spearman p-values cannot be used inferentially due to auto-correlated 5-session forward return labels.

---

## 7. Regression Test Execution Results

The entire automated test suite was executed in verbose mode:

```powershell
python -m pytest -v
```

### Actual Test Results
```text
======================= test session starts =======================
platform win32 -- Python 3.14.6, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\sanja\OneDrive\Documents\Sanjay\Colllege_Projects\Stock_prediction_pinnacle_project\project
plugins: anyio-4.14.1, hydra-core-1.3.4
collected 136 items

tests/test_api.py::test_health_endpoint PASSED                           [  0%]
tests/test_api.py::test_predict_endpoint_valid_payload PASSED            [  1%]
...
tests/test_sec_events.py::test_extract_8k_events_filtering_and_deduplication PASSED [ 63%]
tests/test_sec_events.py::test_sec_ingestor_wrapper PASSED               [ 64%]
tests/test_sec_events.py::test_five_minute_dissemination_buffer PASSED   [ 65%]
tests/test_sec_events.py::test_daylight_saving_transitions PASSED        [ 66%]
tests/test_sec_events.py::test_feature_window_and_missingness_semantics PASSED [ 66%]
...
tests/test_temporal_validation_audit.py::test_internal_alpha_tuning_date_grouping PASSED [ 91%]
tests/test_temporal_validation_audit.py::test_preprocessing_isolation_during_alpha_selection PASSED [ 91%]
tests/test_temporal_validation_audit.py::test_walk_forward_splitter_outer_purge_and_integrity PASSED [ 92%]
tests/test_temporal_validation_audit.py::test_identical_validation_sample_across_model_variants PASSED [ 93%]
...
tests/test_universe.py::test_validator_detects_deliberate_errors PASSED  [100%]

======================= 136 passed, 1 warning in 27.13s =======================
```
- **Total Tests Passed**: **136**
- **Failures**: **0**
- **Skipped**: **0**
- **Warnings**: 1 harmless deprecation warning (`starlette.testclient` httpx deprecation in `test_api.py`).

---

## 8. Remaining Limitations

1. **Unmapped Ticker `AA`**: Corporate succession for Alcoa Inc. / Arconic remains unmapped to a verified CIK; `AA` must remain excluded from production data.
2. **Item-Level Text Ignored**: Full-text and NLP extraction of Exhibit 99.1 press releases were not ingested pursuant to Phase 5E.1 conservative copyright policy. Factual item flags alone do not indicate positive or negative earnings surprise.
3. **Small Cross-Section**: The 4-company panel (`AAPL`, `JPM`, `GOOG`, `TSLA`) is sufficient for proof-of-concept audit, but insufficient to establish generalized multi-modal equity predictability.

---

## 9. Final Acceptance Recommendation

### Verdict: **ACCEPT WITH DOCUMENTED LIMITATIONS**

**Justification**:
1. **Zero Discrepancies**: The walk-forward model comparison artifact reproduces the implementation report numbers with 100% numerical fidelity across all 720 observations.
2. **Authentic Provenance**: All 109 SEC Form 8-K acceptance timestamps are verified against official EDGAR JSON submissions with 0 mismatches or fabrications.
3. **Leakage Protection Verified**: Date grouping and preprocessing isolation inside internal alpha tuning resolve prior cross-validation vulnerabilities and are protected by regression tests.
4. **Honest Limitations Stated**: The documentation explicitly acknowledges that event features provide only a marginal (3 bps) MAE shift, merely match the naive historical median, and offer no proof of commercial profitability.
5. **Clean Test Suite**: All 136 tests pass cleanly with zero regressions.

**Remaining Actions**:
- Maintain ticker `AA` excluded.
- Retain Phase 5F artifacts as the accepted multi-modal benchmark.
- Do not deploy trading rules or claim production readiness without broader cross-asset expansion and non-linear feature architectures in future phases.

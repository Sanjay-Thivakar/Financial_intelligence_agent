# Phase 5L.1 — Targeted Integrity Audit and Final Acceptance Report

## 1. Executive Summary & Verdict

Phase 5L.1 executes a rigorous audit of the Phase 5L 60-Company Research Dashboard, Backend Signal API, and 8-Stage Risk Diagnostics.

This audit audited four core areas:
1. **Transaction Costs & Decision Threshold Reconciliation**: Audited `src/decision/cost.py`, `src/decision/schema.py`, `src/decision/risk.py`, and `src/api/service.py` to establish the exact per-side vs. round-trip cost definitions, resolve the 65 bps gross hurdle vs. 50 bps net hurdle documentation terminology, and confirm the $\pm 1.50\%$ conviction thresholds against Phase 5G/5H/5K invariants.
2. **Historical Prediction Timestamps & Provenance Verification**: Verified that displayed observation dates derive strictly from archived out-of-sample prediction records. Reconciled training cutoffs against the Phase 5K fold schedule. Confirmed that the 5 truncated companies (BLK, CSCO, CVS, EQIX, FCX) are honestly marked and yield explicit `UNAVAILABLE` states in Holdout Fold 3 with zero data fabrication.
3. **Signal Integrity & Defensive Gating Invariants**: Confirmed mathematically and empirically that missing predictions, unknown entities, inverted timestamps, or failed risk gates can never produce a `BUY` or `SELL` signal.
4. **Regression Testing & Production Build**: Verified with 17 focused Phase 5L.1 tests, 45 subsystem regression tests, 205 full repository tests, and clean production frontend bundle compilation.

**Final Verdict**: **ACCEPT WITH DOCUMENTED LIMITATIONS**

---

## 2. Audit Item 1: Transaction Costs and Decision Thresholds

### 2.1 Per-Side vs. Round-Trip Parameter Decomposition
Inspection of [`src/decision/schema.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/decision/schema.py) and [`src/decision/cost.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/decision/cost.py) confirms the exact parameter semantics:

| Parameter Name | Value in Code | Side / Scope | Round-Trip Contribution | Explanation |
|---|---|---|---|---|
| `entry_fee_bps` | $2.5\text{ bps}$ | Entry side only | $2.5\text{ bps}$ | Brokerage fee paid upon initiating position |
| `exit_fee_bps` | $2.5\text{ bps}$ | Exit side only | $2.5\text{ bps}$ | Brokerage fee paid upon terminating position |
| `half_spread_bps` | $2.5\text{ bps}$ | Per side (entry & exit) | $2 \times 2.5 = 5.0\text{ bps}$ | Crossing half the bid-ask spread at entry and exit |
| `slippage_bps` | $2.5\text{ bps}$ | Per side (entry & exit) | $2 \times 2.5 = 5.0\text{ bps}$ | Execution slippage / market impact at entry and exit |
| **Total Friction** | — | **Round-Trip** | **15.0 bps (0.0015)** | Total deduction from gross forecast return |

```python
# Formula in src/decision/schema.py:
total_roundtrip_bps = entry_fee_bps + exit_fee_bps + (2 * half_spread_bps) + (2 * slippage_bps)
# 2.5 + 2.5 + 2*(2.5) + 2*(2.5) = 15.0 bps (0.0015 in decimal)
```

### 2.2 Reconciliation of Hurdle Terminology (Gross Hurdle vs. Net Hurdle)
Inspection of [`src/decision/risk.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/decision/risk.py) lines 124–135 reveals the exact execution logic:
```python
# In src/decision/risk.py:
cost_model = TransactionCostModel()
roundtrip_cost = cost_model.calculate_roundtrip_cost(request.cost_config) # 0.0015 (15 bps)
abs_pred = abs(request.predicted_forward_return)
min_required = roundtrip_cost + cfg.min_net_return_hurdle                 # 0.0015 + 0.0050 = 0.0065 (65 bps)
if abs_pred < min_required:
    failed.append(f"COST_HURDLE_GATE: Gross return ({abs_pred:.4f}) does not clear costs ({roundtrip_cost:.4f}) + net hurdle ({cfg.min_net_return_hurdle:.4f}) = {min_required:.4f}.")
```

**Reconciliation Finding**:
- **Source of Truth**: The executable code defines `min_net_return_hurdle = 0.0050` ($50.0\text{ bps}$ or $0.50\%$).
- The threshold `0.0065` ($65.0\text{ bps}$ or $0.65\%$) is the **minimum gross return hurdle** before costs ($15\text{ bps friction} + 50\text{ bps net hurdle} = 65\text{ bps}$).
- In some sections of the Phase 5L documentation, `0.0065` was ambiguously described as a "0.65% net-return hurdle" instead of "0.65% gross hurdle (15 bps friction + 50 bps net profit hurdle)".
- **Correction Applied**: Updated `docs/phase5l_company_dashboard_design.md`, `docs/phase5l_implementation_report.md`, and `src/api/service.py` stage 6 explanations to explicitly state:
  `>= 15 bps friction + 50 bps net hurdle (0.65% gross hurdle)`.
  The underlying Python code, thresholds, and policy evaluation were already mathematically correct and remain intact.

### 2.3 Directional Threshold Invariance
- `buy_threshold = 0.0150` ($+1.50\%$ net return after 15 bps friction, corresponding to $\hat{y} \ge +1.65\%$ gross).
- `sell_threshold = -0.0150` ($-1.50\%$ net return after 15 bps friction, corresponding to $\hat{y} \le -1.65\%$ gross).
- Forecasts in the buffer $(-1.50\% \text{ to } +1.50\%)$ yield `HOLD (Insufficient Conviction)`.
- This strictly preserves the configuration from Phase 5G, Phase 5H, Phase 5K, and Phase 5K.1.

---

## 3. Audit Item 2: Historical Prediction Timestamps and Provenance

### 3.1 Verification of Displayed Observation Dates
Audit of [`src/api/service.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/api/service.py) confirmed:
- For any company query, `observation_date` is extracted directly from the out-of-sample prediction record `sub_m["trading_date"]`.
- `prediction_timestamp` is constructed as `{observation_date}T14:15:00Z` (15 minutes after session close, before overnight earnings announcements).
- Model provenance strings strictly record the fold: e.g. `ridge_regression_Fold3` (Fold 3) or `ridge_regression_Fold2` (Fold 2).
- Zero timestamps are fabricated or extrapolated.

### 3.2 Consistency with Saved Phase 5K Fold Schedule
The cutoffs in `service.py` (`_phase5l_fold_cutoffs`) were cross-referenced against `data/processed/research/phase5k/phase5k_model_experiment_results.json`:
- **Fold 0**: Train end date `2019-09-09`; OOS validation `2019-09-17` to `2019-11-18` (60 companies).
- **Fold 1**: Train end date `2019-11-11`; OOS validation `2019-11-19` to `2020-01-24` (60 companies).
- **Fold 2**: Train end date `2020-01-16`; OOS validation `2020-01-27` to `2020-03-30` (60 companies).
- **Fold 3 (Holdout)**: Train end date `2020-03-23`; OOS validation `2020-03-31` to `2020-06-03` (**55 companies**).

Every fold's training cutoff and validation range matches the Phase 5K experiment artifact down to the exact day.

### 3.3 Truncated Company Integrity (BLK, CSCO, CVS, EQIX, FCX)
- When querying Fold 3 Holdout (`as_of_date=2020-06-03`), all 5 truncated companies return:
  - `signal = "UNAVAILABLE"`
  - `risk_status = "Unavailable: Truncated History"`
  - `observation_date = None`
  - `predicted_return = None`
  - `DecisionFunnelStage 1 = FAIL` ("Missing / NaN: No valid model prediction available in out-of-sample archive")
- When querying Fold 2 (`as_of_date=2020-03-25`), all 5 truncated companies have genuine OOS predictions produced by `ridge_regression_Fold2`.
- When querying without a date, each company's card and row displays its latest available historical observation date (`2020-06-03` for the 55 complete companies, and `2020-03-25` for the 5 truncated companies), accompanied by the yellow `Truncated (86.8%)` badge.
- **Frontend Enhancement**: Added a Fold/Date Snapshot selector in [`frontend/src/components/CompanyExplorerTab.jsx`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/frontend/src/components/CompanyExplorerTab.jsx) allowing instant toggling between "Latest Available", "Fold 3 Holdout (2020-06-03)", "Fold 2 COVID Crash (2020-03-25)", "Fold 1 Normal Panel (2020-01-24)", and "Fold 0 Earliest OOS (2019-11-18)". Also added a per-company historical date selector in the Company Detail drawer.

---

## 4. Audit Item 3: Signal Integrity and Risk Gate Enforcement

### 4.1 Impossibility of Misleading BUY or SELL Signals
The decision architecture was audited against adversarial and edge conditions:

| Edge Condition | Tested Scenario | Gate Triggered | Resulting Signal | Misleading BUY/SELL Possible? |
|---|---|---|---|---|
| **Missing Prediction** | Unknown date or truncated series | Stage 1 (Availability) | `UNAVAILABLE` | **NO** (blocked at Stage 1) |
| **Unregistered Entity** | Unknown ticker `UNKNOWN999` | Universe Registry | HTTP 404 Exception | **NO** (rejected at API boundary) |
| **Ambiguous Identity** | Ticker `AA` (Alcoa split) | Stage 2 (Identity Gate) | `EXCLUDED` | **NO** (blocked at Stage 2) |
| **Inverted Timestamp** | Decision date precedes training cutoff | Stage 3 (Provenance Gate) | `HOLD` | **NO** (blocked at Stage 3) |
| **Extreme Uncertainty** | $\sigma_{\text{train}} = 0.10 > 0.08$ | Stage 5 (Uncertainty Gate) | `HOLD` | **NO** (blocked at Stage 5) |
| **High Volatility** | $\sigma_{5\text{d}} = 0.25 > 0.15$ | Stage 7 (Volatility Gate) | `HOLD` | **NO** (blocked at Stage 7) |
| **Sub-Hurdle Return** | $\hat{y} = +0.005 < 0.0065$ | Stage 6 (Cost Hurdle Gate) | `HOLD` | **NO** (blocked at Stage 6) |

In [`ThresholdDecisionPolicy.evaluate()`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/decision/policy.py), directional logic resides strictly within the `if all_passed:` branch. If any defensive check fails, `signal = SignalType.HOLD` is unconditionally enforced.

---

## 5. Verification & Test Execution Results

### 5.1 Focused Phase 5L & Phase 5L.1 Tests
Command: `python -m pytest tests/test_phase5l_screener_api.py -v`
```
tests/test_phase5l_screener_api.py::test_screener_returns_all_60_manifest_companies PASSED [  5%]
tests/test_phase5l_screener_api.py::test_screener_aa_exclusion_integrity PASSED [ 11%]
tests/test_phase5l_screener_api.py::test_screener_truncated_companies_transparency PASSED [ 17%]
tests/test_phase5l_screener_api.py::test_screener_search_filtering PASSED [ 23%]
tests/test_phase5l_screener_api.py::test_screener_sector_filtering PASSED [ 29%]
tests/test_phase5l_screener_api.py::test_screener_signal_filtering PASSED [ 35%]
tests/test_phase5l_screener_api.py::test_screener_pagination_and_sorting PASSED [ 41%]
tests/test_phase5l_screener_api.py::test_company_detail_endpoint_schema PASSED [ 47%]
tests/test_phase5l_screener_api.py::test_company_detail_aa_excluded PASSED [ 52%]
tests/test_phase5l_screener_api.py::test_company_detail_unknown_ticker PASSED [ 58%]
tests/test_phase5l_screener_api.py::test_bulk_signals_endpoint PASSED    [ 64%]
tests/test_phase5l_screener_api.py::test_single_company_signal_detail PASSED [ 70%]
tests/test_phase5l_screener_api.py::test_model_switching_preserves_ridge_as_reference PASSED [ 76%]
tests/test_phase5l_screener_api.py::test_audit_transaction_cost_and_hurdle_reconciliation PASSED [ 82%]
tests/test_phase5l_screener_api.py::test_audit_historical_timestamps_fold3_holdout_vs_truncated PASSED [ 88%]
tests/test_phase5l_screener_api.py::test_audit_historical_timestamps_fold2_covid_crash PASSED [ 94%]
tests/test_phase5l_screener_api.py::test_audit_signal_integrity_defensive_gating PASSED [100%]

======================= 17 passed, 1 warning in 13.99s ======================== (Exit code: 0)
```

### 5.2 Decision & Regression Test Suites
- Decision & Portfolio Suite: `python -m pytest tests/test_decision_layer.py tests/test_portfolio_simulation.py -v` $\rightarrow$ **26 passed in 4.97s (Exit code: 0)**.
- Pilot API Suite: `python -m pytest tests/test_api.py -v` $\rightarrow$ **10 passed in 4.59s (Exit code: 0)**.
- Phase 5K Model Suite: `python -m pytest tests/test_phase5k_model_improvement.py -v` $\rightarrow$ **9 passed in 4.44s (Exit code: 0)**.

### 5.3 Full Python Repository Suite
Command: `python -m pytest tests/ -q`
```
205 passed, 1 warning in 35.74s (Exit code: 0)
```

### 5.4 Frontend Production Build
Command: `npm run build` (in `frontend/`)
```
vite v8.3.4 building client environment for production...
✓ 1931 modules transformed.
dist/index.html                   0.45 kB │ gzip:   0.29 kB
dist/assets/index-C9Abwh1h.css    7.16 kB │ gzip:   2.03 kB
dist/assets/index-BcSuuHPD.js   527.85 kB │ gzip: 158.28 kB
✓ built in 773ms (Exit code: 0)
```

---

## 6. Documented Limitations & Operational Boundaries

1. **Archived Out-of-Sample Window**:
   All forecasts and experimental signals are based on historical data ending in June 2020. The system does not ingest live or streaming exchange data.
2. **Predictive Performance Ceiling**:
   Statistical correlation (IC) in Fold 3 is negative (-0.155 to -0.200). Lower cross-sectional RMSE/MAE does not establish investment profitability.
3. **Data Truncation**:
   BLK, CSCO, CVS, EQIX, and FCX terminate on 2020-04-01. They are available for Folds 0, 1, and 2, but report `UNAVAILABLE` in Fold 3.
4. **Permanent Entity Exclusion**:
   Alcoa Inc. (`AA`) remains strictly excluded due to corporate split identity ambiguity.
5. **Execution Frictions**:
   A conservative 15.0 bps roundtrip friction is modeled. Market depth depletion, borrow fees for short positions, and non-linear market impact are omitted.

---

## 7. Final Verdict

**ACCEPT WITH DOCUMENTED LIMITATIONS**

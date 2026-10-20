# Phase 5L — 60-Company Research Dashboard, Signal API & Risk Diagnostics Design

## 1. Executive Summary & Architecture Overview

Phase 5L extends the Financial Intelligence Agent into an institutional research platform supporting the complete 60-company cohort established in Phase 5J and evaluated across walk-forward folds in Phase 5K.

The system delivers three cohesive capabilities:
1. **60-Company Stock Screener**: A responsive, sortable, and filterable research table covering all 60 companies in the validated universe, exposing out-of-sample forward-return forecasts, uncertainty estimates, risk statuses, and policy-governed signals.
2. **Backend Signal API**: Four high-throughput, typed REST endpoints (`/api/research/companies`, `/api/research/companies/{ticker}`, `/api/research/signals`, `/api/research/signals/{ticker}`) providing bulk screening payloads and granular single-ticker diagnostics.
3. **8-Stage Transparent Decision Funnel**: A deterministic diagnostic engine that breaks down every prediction into 8 sequential risk gates and decision checks with explicit numeric metrics, thresholds, and rejection rationales.

```
+-----------------------------------------------------------------------------------------+
|                                60-COMPANY RESEARCH DASHBOARD                            |
|  +---------------------------+  +-------------------------------+  +-----------------+  |
|  | Universe KPI Ribbon (60)  |  | Filter & Search Toolbar (11S) |  | Model Switcher  |  |
|  +---------------------------+  +-------------------------------+  +-----------------+  |
|                                                                                         |
|  [60-Company Screener Table: Ticker | Name | Sector | Coverage | Obs Date | Return | Sig]  |
|                                                                                         |
|  +-----------------------------------------------------------------------------------+  |
|  | SELECTED COMPANY DETAIL VIEW                                                      |  |
|  | +-----------------------+ +-----------------------------------------------------+ |  |
|  | | 250-Bar Price Chart   | | 8-Stage Decision Funnel Diagnostics Cards           | |  |
|  | | Real OHLCV & Volume   | | [Stage 1-8: Status, Metric, Threshold, Explanation] | |  |
|  | +-----------------------+ +-----------------------------------------------------+ |  |
|  +-----------------------------------------------------------------------------------+  |
+-----------------------------------------------------------------------------------------+
                                          |
                                          | REST API (FastAPI)
                                          v
+-----------------------------------------------------------------------------------------+
|                                  BACKEND SIGNAL ENGINE                                  |
|  +---------------------------+  +-------------------------------+  +-----------------+  |
|  | GET /research/companies   |  | GET /research/companies/{tk}  |  | GET /signals    |  |
|  +---------------------------+  +-------------------------------+  +-----------------+  |
|               |                                 |                          |            |
|               v                                 v                          v            |
|  +-----------------------------------------------------------------------------------+  |
|  | ThresholdDecisionPolicy: 15 bps Friction | 0.0800 Uncertainty | 0.1500 Volatility |  |
|  +-----------------------------------------------------------------------------------+  |
|               |                                 |                          |            |
|               v                                 v                          v            |
|  [phase5j_company_eligibility.csv] [phase5k_predictions_oos.parquet] [phase5i_market]   |
+-----------------------------------------------------------------------------------------+
```

---

## 2. 60-Company Cohort Definition & Data Invariants

### 2.1 Universe Manifest
The universe is strictly bounded to the 60 validated corporate entities defined in `data/processed/universe/phase5j_company_eligibility.csv`. These entities span 11 GICS sectors:
- **Information Technology** (6): AAPL, MSFT, NVDA, INTC, CSCO, AMD
- **Financials** (6): JPM, BAC, WFC, GS, MS, BLK
- **Health Care** (6): JNJ, PFE, BMY, MRK, ABT, CVS
- **Consumer Discretionary** (6): AMZN, TSLA, HD, MCD, NKE, SBUX
- **Consumer Staples** (6): PG, KO, PEP, WMT, COST, MO
- **Energy** (6): XOM, CVX, COP, SLB, EOG, MPC
- **Utilities** (6): NEE, DUK, SO, D, AEP, EXC
- **Industrials** (6): CAT, GE, UNP, HON, BA, MMM
- **Materials** (6): LIN, APD, ECL, SHW, FCX, NEM
- **Real Estate** (6): PLD, AMT, CCI, EQIX, PSA, SPG

### 2.2 Strict Ticker Exclusion: AA (Alcoa Inc. / Arconic Inc.)
Candidate ticker `AA` is permanently audited as **EXCLUDED**. In November 2016, original Alcoa Inc. underwent a tax-free corporate split into Arconic Inc. (retaining CIK `0000004281` and pre-split operating history) and a newly spun-off Alcoa Corp (assigned new CIK `0001675149`, adopting ticker `AA`). Splicing pre-split price/accounting series across the spin-off event violates fundamental temporal identity invariants. Querying `AA` via the screener or detail API produces a clean HTTP 200 payload with `coverage_status="EXCLUDED"`, `signal="EXCLUDED"`, Stage 2 Funnel failure, and no fabricated returns.

### 2.3 Honest Data Truncation (BLK, CSCO, CVS, EQIX, FCX)
Five companies experienced market data truncation on 2020-04-01 (completeness: 86.78%, 315 out of 363 sessions). While eligible for Walk-Forward Folds 0, 1, and 2, their series terminated before Fold 3 (Holdout window). Rather than imputing or extrapolating missing sessions, the screener flags them as `is_truncated=True`, labels their risk status as `Unavailable: Truncated History` when querying Fold 3, and presents transparent truncation notes.

---

## 3. Backend Signal API Specification

### 3.1 Endpoint Routing

| Method | Route | Description | Query Parameters |
|---|---|---|---|
| `GET` | `/api/research/companies` | 60-Company Screener bulk payload with live signals and risk gates | `model_id`, `as_of_date`, `sector`, `signal`, `coverage`, `search`, `sort_by`, `sort_dir`, `limit`, `offset` |
| `GET` | `/api/research/companies/{ticker}` | Comprehensive company research profile, 8-stage funnel, and 250-bar historical OHLCV chart | `model_id`, `as_of_date` |
| `GET` | `/api/research/signals` | Cohort-wide signal table and distribution summary | `model_id`, `as_of_date`, `sector`, `signal` |
| `GET` | `/api/research/signals/{ticker}` | Granular decision contract and risk gate outcomes for a single company | `model_id`, `as_of_date` |

### 3.2 Model Reference Invariant
The default model for all endpoints is strictly locked to `ridge_regression` (the Phase 5J walk-forward baseline). Alternative candidate models evaluated in Phase 5K (`hist_gradient_boosting`, `elastic_net`, `ridge_cs_demeaned`, `ridge_cs_scaled`, `ridge_sector_neutral`, `zero_baseline`, `median_baseline`) can be explored via explicit query parameters, but **none are promoted to default**.

---

## 4. The 8-Stage Transparent Decision Funnel

Every prediction is subjected to an 8-stage decision funnel implemented via `ThresholdDecisionPolicy` with zero threshold loosening:

| Stage # | Stage Name | Verification Condition | Applied Threshold | Outcome States |
|---|---|---|---|---|
| **Stage 1** | **Forecast Availability & Validity** | Prediction exists in out-of-sample archive and is a finite real number | Real Number | `PASS` / `FAIL` |
| **Stage 2** | **Company Identity & Exclusion Gate** | Legal entity identity resolved; not in permanent exclusion registry | Non-Ambiguous CIK | `PASS` / `FAIL` |
| **Stage 3** | **Model Provenance & Temporal Cutoff** | Observation timestamp strictly follows model training cutoff date | Non-Inverted Time | `PASS` / `FAIL` |
| **Stage 4** | **Feature Completeness & Freshness** | All 17 technical indicators present with zero lookahead | 17 Valid Features | `PASS` / `FAIL` |
| **Stage 5** | **Forecast Uncertainty Gate** | Historical residual standard deviation $\sigma_{\text{train}}$ below ceiling | $\sigma \le 0.0800$ (8.00%) | `PASS` / `FAIL` |
| **Stage 6** | **Cost & Net Return Hurdle Gate** | Gross return $|\hat{R}|$ clears friction + net hurdle | Gross Hurdle $\ge 0.0065$ (0.65%) | `PASS` / `FAIL` |
| **Stage 7** | **Market Volatility Gate** | 5-session rolling price volatility $\sigma_{5\text{d}}$ below stress ceiling | $\sigma_{5\text{d}} \le 0.1500$ (15.00%) | `PASS` / `FAIL` |
| **Stage 8** | **Directional Decision Gate** | Net return crosses calibrated conviction buffer | BUY $\ge +1.50\%$ / SELL $\le -1.50\%$ | `PASS` / `HOLD` |

### 4.1 Cost Model Calibration
Friction is modeled at a conservative institutional standard:
- **Brokerage Commission**: 2.5 bps entry + 2.5 bps exit (5.0 bps roundtrip).
- **Bid-Ask Spread**: 2.5 bps half-spread entry + 2.5 bps half-spread exit (5.0 bps roundtrip).
- **Execution Slippage**: 2.5 bps entry + 2.5 bps exit (5.0 bps roundtrip).
- **Total Roundtrip Friction**: **15.0 bps (0.0015)**.
- **Minimum Net Economic Hurdle**: **50.0 bps (0.0050)** net after all frictions.
- **Minimum Gross Return Hurdle**: **65.0 bps (0.0065)** ($15\text{ bps friction} + 50\text{ bps net hurdle}$).

---

## 5. Signal Semantics & Governance

### 5.1 Meaning of Signals
- **`BUY`**: Model forecasts a 5-session return exceeding $+1.50\%$ net of transaction costs, and all 7 preceding risk gates have evaluated to `PASS`.
- **`HOLD (Risk-Gated)`**: Model predicted return was directional, but one or more risk gates failed (e.g., market volatility exceeded 15%, or uncertainty exceeded 8%).
- **`HOLD (Insufficient Conviction)`**: All risk gates passed, but predicted net return was within the neutral band ($-1.50\%$ to $+1.50\%$).
- **`SELL`**: Model forecasts a 5-session negative return exceeding $-1.50\%$ net of costs, with all risk gates passed. (Documented as an experimental signal; short selling carries borrow fee and margin requirements not modeled).
- **`UNAVAILABLE`**: Observation date lacks valid out-of-sample prediction (e.g. truncated history or dates outside evaluation window).
- **`EXCLUDED`**: Entity identity unresolved (AA).

### 5.2 Regulatory & Research Disclaimers
1. **Archived Out-of-Sample Data**: All signals and forecasts derive from historical out-of-sample walk-forward partitions ending in June 2020.
2. **No Real Execution**: No orders are placed, routed, or simulated against live exchange order books.
3. **No Advice**: The dashboard does not provide personalized investment advice or recommendations.
4. **No Established Stock Selection**: Walk-forward IC values (-0.155 to -0.200 in Fold 3) confirm that statistical predictions in this regime do not establish profitable trading ability.

---

## 6. Frontend UI / UX Architecture

The user interface is built in React within `frontend/src/components/CompanyExplorerTab.jsx`:
- **Historical Notice Banner**: Top warning emphasizing archived 2019-2020 data.
- **Model Switcher**: Allows toggling between Ridge, GBRT, ElasticNet, Demeaned, and Baselines.
- **KPI Summary Ribbon**: Displays total cohort (60), active filter count, and live counts for BUY, HOLD, SELL, and UNAVAILABLE.
- **Filter Toolbar**: Search by ticker/name, 11 GICS sector dropdown, signal dropdown, coverage filter, and risk status filter.
- **Responsive Table**: Sortable column headers with visual sort indicators, pagination buttons (15, 25, 50, 60 per page), and color-coded signal badges with accessible secondary text.
- **Company Detail Drawer / Modal**:
  - Entity metadata (CIK, sector, total sessions, coverage).
  - Native SVG Candlestick & Volume chart rendering up to 250 historical bars directly from `phase5i_market_expansion.parquet`.
  - 8-stage decision funnel visual diagnostic cards showing exact metric values, thresholds, and explanatory text.
  - 15 bps fee breakdown table and data quality warning alerts.

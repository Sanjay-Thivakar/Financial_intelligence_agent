# Financial Intelligence Agent — Prototype Dashboard Guide

## 1. Overview & Visual Architecture
The Financial Intelligence Agent Prototype Dashboard is an institutional-grade dark financial terminal engineered for quantitative investment research. It integrates three information layers:
1. Historical S&P 500 Market Quotes & Engineered Technical Indicators.
2. SEC EDGAR Point-in-Time Financial Fundamentals (with restatement safety and zero lookahead bias).
3. Licensed Financial News & Event Headlines.

Visual Style: **Premium Dark Financial Terminal** with near-black/navy palette (`#070a0f`, `#0c1017`), crisp monospace tabular typography (`JetBrains Mono`), subtle borders (`#1c2638`), and responsive data-dense layouts.

---

## 2. Startup Instructions

### 2.1 Backend API Server (FastAPI + Uvicorn)
The backend provides typed REST endpoints, CORS middleware, and serves the pre-built React SPA static bundle from `frontend/dist`.

From the project root:
```bash
# Start FastAPI backend server on port 8000
python -m uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload
```
API Documentation (Swagger UI) is available at: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
Unified SPA is served directly at: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)

### 2.2 Frontend Development Server (Optional Vite Dev Mode)
If actively developing frontend React components with Hot Module Replacement (HMR):
```bash
cd frontend
npm run dev
```
The Vite dev server will start at [http://localhost:5173/](http://localhost:5173/) and proxy `/api` requests to `http://127.0.0.1:8000`.

### 2.3 Production Build
To rebuild the frontend static distribution:
```bash
cd frontend
npm run build
```

---

## 3. Environment Variables
The application relies on offline verified Parquet files in `data/processed/`. If external SEC or Tiingo services are queried via offline pipelines, the following environment variables are referenced by name only:
- `SEC_EDGAR_USER_AGENT`: Declarative User-Agent for SEC EDGAR compliance (`SampleCompany AdminContact@domain.com`).
- `TIINGO_API_KEY`: API token for market data synchronization.
- `APP_ENV`: Environment designation (`development` or `production`).

No secrets or credentials are hardcoded into source files or dashboard bundles.

---

## 4. Screen-by-Screen Data Provenance & Behavior

| Screen / View | Data Source / Pipeline | Provenance & Nature | Guardrails & Fallbacks |
| :--- | :--- | :--- | :--- |
| **Overview** | `data/processed/market/sp500_market_sample.parquet` | **Real Historical Data** (Quotes up to 2023-12-28). | Stale/historical observation banner; never simulates live price feeds. |
| **Company Explorer** | Verified Entity Catalog & SEC CIK master | **Verified Metadata** for AAPL, JPM, GOOG, TSLA. | **AA is strictly excluded** with clear explanation of the 2016 Alcoa/Arconic split. |
| **Market Charts** | `MarketFeatureEngine` & `ForwardReturnTargetEngine` | **Computed Features** (SMA-20, SMA-50, RSI-14, 21d Volatility, 5d Target). | Ratio adjustment factor used for opening prices; empty data handled gracefully. |
| **Model Lab** | Phase 5D Walk-Forward Audit Report (`docs/phase5d_sec_fundamentals_baseline_report.md`) | **Report-Derived Results** (Audited 4-fold walk-forward holdout MAE). | Labeled: `Report-derived result from Phase 5D walk-forward evaluation — not recomputed in this session`. Prominent disclaimer that lower prediction MAE $\neq$ trading profit. |
| **Prediction Research** | `POST /api/models/predict` (Model 1: Market-Only Ridge) | **Genuine Experimental Prediction** on session T close features. | Returns honest `status="unavailable"` if data is missing or ticker excluded (e.g. AA). **No fake BUY/HOLD/SELL signals**. |

---

## 5. Walk-Forward Evaluation Architecture & Scores

### Target Definition:
5-trading-session forward return:
$$y_T^{(5)} = \frac{P_{T+5, \text{close}}^{\text{adj}} - P_{T+1, \text{open}}^{\text{adj}}}{P_{T+1, \text{open}}^{\text{adj}}}$$
Decision at session $T$ close, executable entry at $T+1$ open, exit at $T+5$ close.

### 5-Session Purge Invariant:
An exact 5-trading-day purge gap separates the end of training labels from validation decision dates to guarantee zero label overlap.

### Phase 5D Final Holdout (Fold 3: 2020-03-31 to 2020-06-03) Performance:
- **Reference 0 (Naive Zero Return)**: MAE `0.0536` | RMSE `0.0773` | Hit Rate `50.0%`
- **Reference 1 (Historical Median)**: MAE `0.0502` | RMSE `0.0738` | Hit Rate `72.8%`
- **Model 1 (Market-Only Ridge)**: MAE `0.0497` | RMSE `0.0732` | Hit Rate `70.0%` (Winner on MAE)
- **Model 2 (Market + Fundamentals Ridge)**: MAE `0.0504` | RMSE `0.0740` | Hit Rate `67.2%`

---

## 6. Known Limitations & Roadmap

1. **Phase 5E.1 License Corrections Pending**:
   Historical news text redistribution and licensing restrictions currently restrict news features to headline-only pilot research.
2. **Phase 5F SEC Event Extraction Unimplemented**:
   Form 8-K event parsing and Exhibit 99.1 item classifications are scheduled for Phase 5F and are not yet active in this prototype.
3. **Absence of Trading Decision Layer**:
   Predictive models generate continuous forward-return point estimates. No portfolio optimization, execution slippage modeling, borrowing cost deduction, or discrete BUY/HOLD/SELL recommendation engine exists.

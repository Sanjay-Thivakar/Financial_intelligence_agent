# Financial Intelligence Agent: US Equities Research Framework

An open, modular framework designed to evaluate how different financial information modalities (market prices, SEC 10-K/10-Q filings, earnings call transcripts, news sentiment, macro feeds) contribute to risk-aware **BUY / HOLD / SELL** investment decisions.

---

## Prototype Dashboard & Research Terminal (Phase 6 Integrated)

The quantitative research terminal provides unified cross-tab analysis across five core modules:
1. **Overview**: Company capability inventory, CIK identity, historical observation bounds, and recent session returns.
2. **Market Charts**: Verifiable historical split-adjusted prices (2018–2023 for pilot; 1980–2023 for cohort; 2017–2020 for truncated), SMA 20/50, and 14-day RSI overlays.
3. **Model Lab**: Walk-forward benchmark evaluations (Phase 5D, 5J, 5K) and institutional multi-asset simulation summaries.
4. **Prediction Research**: Archived out-of-sample forward-return predictions (Phase 5K) and isolated 4-company prototype runtime inference.
5. **60-Company Screener**: Full 60-company research cohort with 8-stage risk gating, transaction cost deductions (15 bps round-trip invariant), and direct cross-tab navigation.

### Quickstart

```bash
# 1. Start FastAPI backend (Port 8000)
python -m uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload

# 2. Start Vite frontend dev server (Port 5173)
cd frontend
npm run dev

# 3. Open terminal in browser
# http://localhost:5173/?ticker=CAT&tab=market-charts
```

### Verification & Testing Commands

```bash
# Backend Pytest Regression Suites (87 core tests + 35 research tests, 100% pass)
python -m pytest tests/test_phase6_market_layer.py tests/test_phase6_capability_contract.py tests/test_phase6_prediction_research.py tests/test_api.py tests/test_phase5l_screener_api.py tests/test_storage_policy_and_interface.py -v

# Frontend Unit Tests (13/13 pass)
cd frontend && npm test

# Frontend Production Build & Code-Splitting Check
cd frontend && npm run build
```

### Research Architecture & Data Invariants

1. **Strict Runtime vs Archived Separation**:
   - **Runtime Inference (`/api/models/predict`)**: Only supported for the 4 pilot companies (`AAPL`, `JPM`, `GOOG`, `TSLA`). Non-prototype companies return a transparent `status: "unavailable"` message rather than fabricating outputs.
   - **Archived Research Predictions (`/api/research/companies/{ticker}/predictions`)**: Sourced directly from immutable walk-forward holdout parquet artifacts (`data/processed/research/phase5k/phase5k_predictions_oos.parquet`).
2. **Offline Data Boundaries & Truncation**:
   - 55 companies have complete historical observations through 2023 (or full evaluation window).
   - 5 companies (`BLK`, `CSCO`, `CVS`, `EQIX`, `FCX`) have truncated historical market records ending on **2020-04-01 (315 trading sessions)**. They are transparently badged as `TRUNCATED` across all views.
3. **Corporate Identity Safeguards**:
   - **AA (Alcoa)**: Strictly excluded across all market, prediction, and capability endpoints due to corporate split ambiguity (Nov 2016 division into Arconic Inc. [ARNC] and Alcoa Corp [AA]).
   - **GOOGL**: Rejected with HTTP 404 and explicit guidance pointing to canonical Class C constituent `GOOG`.
4. **No Live Feeds / No Investment Advice**: All data represents static, reproducible offline historical datasets. None of the signals constitute personalized investment advice.


---

## Phase 1: S&P 500 Universe & Company-Identity Layer

Phase 1 establishes the point-in-time universe of S&P 500 constituents and canonical company identities spanning **1996 through present**. It ensures historical experiments avoid survivorship bias and look-ahead contamination.

### Project Structure

```text
├── data/
│   ├── raw/
│   │   └── universe/                    # Pristine scraped & downloaded raw sources
│   │       ├── retrieval_metadata.json  # Download manifest with timestamps & hashes
│   │       ├── wikipedia_current_constituents.csv / .json
│   │       ├── wikipedia_historical_changes.csv / .json
│   │       ├── sp500_ticker_start_end_raw.csv
│   │       ├── hanshof_sp500_constituents_raw.csv
│   │       └── sec_company_tickers_raw.json
│   └── processed/
│       └── universe/                    # Canonical processed deliverables
│           ├── sp500_universe.parquet   # High-performance Parquet format
│           ├── sp500_universe.csv       # Human-readable CSV format
│           ├── universe_data_quality_report.json
│           └── universe_data_quality_report.md
├── src/
│   └── data/
│       └── universe/                    # Modular Python library
│           ├── __init__.py
│           ├── fetcher.py               # Raw data fetcher with polite SEC/Wiki headers
│           ├── ticker_mapping.py        # Ticker normalization, transitions & CIK lookup
│           ├── builder.py               # Canonical universe constructor & PIT query
│           ├── validator.py             # Data quality validator
│           └── exporter.py              # Parquet, CSV, and report exporter
├── scripts/
│   ├── build_universe.py                # End-to-end universe build CLI
│   └── validate_universe.py             # Standalone universe validator CLI
├── docs/
│   └── README.md                        # Complete Phase 1 documentation & data dictionary
└── tests/
    └── test_universe.py                 # Pytest test suite
```

---

## Quickstart

### 1. Build the Universe Pipeline
To execute the end-to-end pipeline (fetch $\to$ build $\to$ validate $\to$ export):

```bash
python scripts/build_universe.py
```

Options:
- `--fetch`: Force re-downloading raw sources from remote endpoints.
- `--raw-dir <path>`: Custom raw data directory.
- `--processed-dir <path>`: Custom output directory.

### 2. Validate Processed Data
To run validation against an existing dataset:

```bash
python scripts/validate_universe.py --file data/processed/universe/sp500_universe.parquet
```

### 3. Run Unit & Integration Tests

```bash
python -m pytest -v tests/test_universe.py
```

---

## Survivorship Bias Prevention

To query the exact constituents as of any historical date (e.g. `2008-09-15`):

```python
import pandas as pd
from src.data.universe.builder import UniverseBuilder

universe = pd.read_parquet("data/processed/universe/sp500_universe.parquet")
pit_constituents = UniverseBuilder.get_constituents_at_date(universe, "2008-09-15")

print(f"Constituents on 2008-09-15: {len(pit_constituents)}")
# Correctly includes historical constituents (e.g. Lehman Brothers LEHMQ, Bear Stearns)
```

For complete methodology, transformations, and schema details, see [`docs/README.md`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/docs/README.md).

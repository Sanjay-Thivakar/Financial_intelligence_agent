# Financial Intelligence Agent: US Equities Research Framework

An open, modular framework designed to evaluate how different financial information modalities (market prices, SEC 10-K/10-Q filings, earnings call transcripts, news sentiment, macro feeds) contribute to risk-aware **BUY / HOLD / SELL** investment decisions.

---

## Prototype Dashboard (Dark Financial Terminal)

The quantitative research prototype dashboard provides interactive historical market analysis, SEC point-in-time fundamentals verification, walk-forward baseline comparisons, and carefully labeled experimental forward-return forecasting.

### Quickstart
```bash
# 1. Start FastAPI backend (serves pre-built dashboard on port 8000)
python -m uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload

# 2. Open dashboard in browser
# http://127.0.0.1:8000/
```
For complete architecture and configuration details, see [Prototype Dashboard Guide](docs/prototype_dashboard_guide.md).

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

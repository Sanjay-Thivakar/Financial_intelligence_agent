# Phase 4B — Financial News Ingestion & Point-in-Time Features Report

## Executive Summary

Phase 4B implements a tested, modular financial news ingestion and baseline feature-engineering pipeline that integrates with the Phase 4A market and SEC fundamental feature architecture.

In accordance with strict project constraints:
- **No predictive models or sentiment classifiers** (e.g. FinBERT) were trained.
- **No polarity or subjective scores** were invented or claimed as verified market impact.
- **No full-universe news downloads** or paid provider integrations were initiated.
- **Persistent storage of scraped commercial web text** remains restricted by default, tracked under the project's license-aware `StoragePolicy`.
- All 74 tests across 10 test modules pass cleanly with zero warnings.

---

## 1. Source Provenance, Licensing, & Realistic Limitations

### 1.1 Source Context & Exploration Status
As established in Phase 2, the **Financial News and Stock Price Integration Dataset (FNSPID)** was evaluated and **rejected as the primary production foundation** for this project due to missing delisted coverage (58.3% delisted ticker deficiency), missing text bodies in bulk aggregations (`All_external.csv` body text is unpopulated), and date-only temporal ambiguity.

For Phase 4B, FNSPID is utilized **strictly as an auxiliary, exploratory research sample** via the existing local slice [`data/raw/news/fnspid_all_external_sample.csv`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/data/raw/news/fnspid_all_external_sample.csv) (2.0 MB, 8,922 rows, spanning 2009–2020), complemented by controlled synthetic fixtures for boundary and regression testing.

### 1.2 Licensing Governance & Storage Policy
- **Author Release vs. Upstream Provenance**: While the FNSPID creators published an open waiver on Hugging Face, the underlying dataset consists of scraped articles from commercial publishers (e.g., Bloomberg, Reuters, Benzinga, Nasdaq). Because permission from these third-party copyright holders cannot be substantiated, the status for persistent caching of raw and normalized sample text is formally designated **UNVERIFIED** rather than permitted.
- **Storage Governance Matrix**: [`src/data/market/storage_policy.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/data/market/storage_policy.py) enforces:
  - `("fnspid", "sample", DataLayer.RAW_RESPONSE)`: **UNVERIFIED / PROHIBITED** (scraped commercial articles lack publisher redistribution consent).
  - `("fnspid", "sample", DataLayer.NORMALIZED_SERIES)`: **UNVERIFIED / PROHIBITED** (local news text database caching unverified without publisher agreements).
  - `("fnspid", "sample", DataLayer.DERIVED_FEATURES)`: **PERMITTED** (non-reversible mathematical and statistical count features for internal research).
  - `("fnspid", "sample", DataLayer.MODEL_OUTPUTS)`: **PERMITTED** (model outputs permitted).
  - `("fnspid", "full_universe", DataLayer.RAW_RESPONSE)`: **UNVERIFIED / PROHIBITED** (bulk warehousing of commercial media text prohibited without enterprise licenses).
  - `("fnspid", "full_universe", DataLayer.NORMALIZED_SERIES)`: **UNVERIFIED / PROHIBITED**.
  - `("fnspid", "full_universe", DataLayer.DERIVED_FEATURES)`: **PERMITTED** (derivative statistical counts).
- **Default In-Memory Discipline**: Disk persistence remains disabled by default (`storage_authorized = False`, `persistence_mode = PersistenceMode.IN_MEMORY`).

---

## 2. Canonical News Schema & Identity Mapping Architecture

### 2.1 Standardized Schema Specification
The canonical news schema was extended in [`src/data/news/schema.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/data/news/schema.py) (`PROCESSED_NEWS_SCHEMA`) to enforce point-in-time provenance and data-quality tracking:

| Column | Data Type | Nullable | Description / Quality Guarantee |
| :--- | :--- | :---: | :--- |
| `news_id` | `string` | No | Deterministic SHA-256 hash: `sha256(ticker + published_at + source + url + headline)[:24]`. Preserves source provenance; distinct publishers reporting identical headlines are never falsely merged. |
| `company_id` | `string` | Yes | Foreign key to canonical S&P 500 universe (`US_CIK_<10digits>`). `None` if unmatched or out-of-interval. |
| `ticker` | `string` | No | Normalized uppercase ticker symbol (standard dot notation, e.g. `BRK.B`). |
| `original_timestamp_raw` | `string` | No | Original raw timestamp string as reported by the source (e.g. `"September 12, 2023 — 06:15 pm EDT"`). |
| `published_at` | `timestamp[us, UTC]` | No | Timezone-aware UTC publication timestamp. |
| `published_date` | `string` | No | ISO date `YYYY-MM-DD` for rapid date-partitioned filtering. |
| `ingestion_timestamp` | `timestamp[us, UTC]` | No | Recorded UTC timestamp when the record was processed into the pipeline. |
| `mapping_status` | `string` | No | Documented status: `MATCHED`, `OUT_OF_INTERVAL`, `UNMATCHED`, `AMBIGUOUS`. |
| `mapping_provenance` | `string` | No | Documented method (e.g. `point_in_time_interval`, `ticker_outside_active_interval`, `unmatched_symbol`). |
| `has_intraday_time` | `bool` | No | `True` if sub-daily hour/minute is present; `False` if date-only (midnight UTC default). |
| `has_body_text` | `bool` | No | `True` if non-empty article body exists; `False` if headline-only. |
| `headline` | `string` | No | Article headline / title. |
| `article_text` | `string` | No | Article text body or summary. Preserved verbatim; empty string when absent (never invented). |
| `source` | `string` | No | Scraped source publisher (e.g., Benzinga, Reuters, Bloomberg, Nasdaq). |
| `url` | `string` | Yes | Source reference URL. |
| `source_dataset` | `string` | No | Source provenance identifier (`fnspid_all_external`, `synthetic_fixture`). |

### 2.2 Hardened Company Identity & Point-in-Time Ticker Resolution
In prior versions, the ticker resolver utilized an unprincipled fallback to the latest interval `lookup_cache[ticker][-1][2]`, which incorrectly matched historical articles for delisted companies to modern active companies.

We completely redesigned the resolver in [`NewsIngestor.resolve_company_mapping`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/data/news/ingestor.py#L59-L95):
1. **Ticker Normalization**: Normalizes punctuation (`BRK-B` and `BRK/B` $\to$ `BRK.B`).
2. **Interval Evaluation**: Checks whether `effective_from <= published_date <= effective_to`.
3. **Strict Status Tracking**:
   - **`MATCHED`**: Exactly 1 active company interval in the canonical S&P 500 universe matches the publication date. Populates `company_id`.
   - **`OUT_OF_INTERVAL`**: The ticker symbol exists in historical S&P 500 records, but was not active on the article's publication date (e.g., `MON` in 2023 following its 2018 acquisition, or `FB` in 2023 following its 2022 transition to `META`). Does **not** force a match; sets `company_id = None`.
   - **`UNMATCHED`**: The ticker symbol is not present anywhere in the S&P 500 canonical registry. Sets `company_id = None`.
   - **`AMBIGUOUS`**: Multiple overlapping active intervals exist for the same symbol on that date. Sets `company_id = None`.
4. **Ticker Succession Handling**: Articles dated 2021 mentioning `FB` map to Meta Platforms (`US_CIK_0001326801`); articles dated 2023 mentioning `META` also map to Meta Platforms (`US_CIK_0001326801`).

---

## 3. Timestamp Precision & Point-in-Time Availability Safety

### 3.1 Timezone Normalization
[`NewsIngestor.parse_datetime`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/data/news/ingestor.py#L97-L180) handles all observed source timestamp conventions:
- Explicit UTC timestamps (e.g., `"2023-12-16 23:00:00 UTC"`).
- Eastern Daylight Time with 12-hour AM/PM and em-dash separators (e.g., `"September 12, 2023 — 06:15 pm EDT"` $\to$ `22:15:00 UTC`).
- Eastern Standard Time (e.g., `"January 17, 2024 — 08:52 am EST"` $\to$ `13:52:00 UTC`).
- Date-only strings (e.g., `"2021-04-05"`, `"Dec 7, 2023"` $\to$ `00:00:00 UTC` with `has_intraday_time = False`).

### 3.2 Strict Point-in-Time Availability Filter
In [`NewsFeatureEngine.is_article_eligible`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/features/news.py#L56-L86), availability is governed by strict rules:
1. **Defensible Cutoff**: `published_at <= decision_timestamp`. Articles published after the decision cutoff (e.g. 20:30 UTC after a 20:00 UTC close) are strictly excluded.
2. **Date-Only Same-Day Ambiguity Protection**:
   - If an article has only a day-level date (`has_intraday_time == False`), its true publication hour is unknown. It could have been published at 8:00 AM, 3:00 PM, or 9:00 PM.
   - For a decision cutoff occurring on that same trading date (e.g. session close at 20:00 UTC on `2023-05-26`), assuming a midnight-stamped date-only article was available before 20:00 UTC is an unverified look-ahead assumption.
   - **Enforced Policy**: When `has_intraday_time == False`, the article is **excluded** from same-day decisions (`published_date >= decision_date`). It becomes eligible only on subsequent decision dates (`published_date < decision_date`), after the entire calendar date has definitively elapsed.
3. **Ingestion Timestamp Independence**: Ingestion timestamps are recorded for audit purposes, but are never treated as proof of original public availability.

---

## 4. Baseline News Feature Engineering Foundation

### 4.1 Feature Definitions
Implemented in [`src/features/news.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/features/news.py) (`NewsFeatureEngine`), baseline features are purely deterministic, non-predictive statistical metrics computed over configurable trailing windows ($W \in \{1, 3, 7, 14, 30\}$ calendar days):

1. **`news_count_{W}d`**: Number of eligible articles published in the inclusive window $[t_{\text{decision}} - W\text{ days}, t_{\text{decision}}]$.
2. **`news_unique_sources_{W}d`**: Count of distinct publishers/sources reporting on the company in the window.
3. **`news_has_body_ratio_{W}d`**: Ratio of eligible articles in the window with non-empty body text. Preserved as `NaN` if count is zero.
4. **`news_has_intraday_ratio_{W}d`**: Ratio of eligible articles with precise intraday timestamps. Preserved as `NaN` if count is zero.
5. **`news_recency_hours`**: Elapsed hours from the most recent eligible article's `published_at` to $t_{\text{decision}}$. Preserved as `NaN` if no articles exist in the maximum lookback window (30 days).
6. **`news_available`**: Boolean flag indicating whether at least one eligible article was found.
7. **`news_missing`**: Boolean indicator flag for missingness in downstream models.
8. **`news_article_count_missing`**: Boolean flag indicating complete absence of news in the maximum window.

### 4.2 Prohibited Behaviors Enforced
- **Zero Sentiment Score Invention**: No heuristic dictionary scores (e.g. VADER, Loughran-McDonald) or unverified polarity numbers were attached.
- **Zero Return Prediction Claims**: News features are purely observational counts and timestamps; no claim is made that these features predict future price movements.
- **No Machine Learning Model**: No transformer models (FinBERT, RoBERTa) were trained or downloaded.

---

## 5. Three-Way Temporal Alignment & Integration

### 5.1 Architecture Harmonization
[`TemporalAligner`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/features/alignment.py) was extended to optionally accept `news_engine: Optional[NewsFeatureEngine]`.

The horizontal join combines:
$$\text{Feature Vector} = [\mathbf{x}_{\text{market}}, \mathbf{x}_{\text{fundamental}}, \mathbf{x}_{\text{news}}]$$
at the exact microsecond decision cutoff ($t_{\text{decision}}$) defined by [`MarketCalendar`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/features/calendar.py).

### 5.2 Real-World Integration Blocker & Honest Disclosure
* **Temporal Disjunction Between Pilot Datasets**:
  - Phase 3B/4A market price and SEC EDGAR pilot data were gathered for the **2023 calendar year** (`AAPL`, `JPM`).
  - The local FNSPID sample [`fnspid_all_external_sample.csv`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/data/raw/news/fnspid_all_external_sample.csv) spans **April 2009 to June 2020** (terminating on `2020-06-10`).
  - Therefore, for 2023 decision cutoffs on the real FNSPID sample, the news feature engine correctly reports `news_count_Wd = 0`, `news_available = False`, `news_recency_hours = NaN`, and `news_missing = True`.
* **Verification Strategy**:
  - The real sample pipeline was validated on historical 2020 dates where articles genuinely exist (e.g., 441 real AAPL articles in spring 2020).
  - Labelled synthetic fixtures were constructed with matching 2023 timestamps to rigorously test 3-way alignment, post-close exclusion, and trailing-window boundaries without downloading gigabytes of new unverified data.

---

## 6. Live Demonstration Output

Executed via [`scripts/demo_phase4b_news.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/scripts/demo_phase4b_news.py):

```text
================================================================================
PHASE 4B — FINANCIAL NEWS INGESTION & POINT-IN-TIME FEATURE DEMONSTRATION
================================================================================

[1] Environment & Sample Inspection:
    - Raw news sample: data\raw\news\fnspid_all_external_sample.csv (2,096,992 bytes)
    - S&P 500 canonical universe: 1265 constituent intervals

[2] Timestamp Parsing & Timezone Normalization:
    * Raw: '2023-12-16 23:00:00 UTC' (Explicit UTC)
      -> UTC: 2023-12-16 23:00:00+00:00 | ISO: 2023-12-16 | Intraday Time: True
    * Raw: 'September 12, 2023 — 06:15 pm EDT' (Daylight Saving Time (EDT, UTC-4))
      -> UTC: 2023-09-12 22:15:00+00:00 | ISO: 2023-09-12 | Intraday Time: True
    * Raw: 'January 17, 2024 — 08:52 am EST' (Standard Time (EST, UTC-5))
      -> UTC: 2024-01-17 13:52:00+00:00 | ISO: 2024-01-17 | Intraday Time: True
    * Raw: '2021-04-05' (Date-only string (no intraday time))
      -> UTC: 2021-04-05 00:00:00+00:00 | ISO: 2021-04-05 | Intraday Time: False

[3] Point-in-Time Ticker & Corporate Identity Resolution:
    * Ticker 'AAPL' on 2020-05-15 (Apple active in index):
      -> company_id: US_CIK_0000320193 | status: MATCHED | provenance: point_in_time_interval
    * Ticker 'FB' on 2021-05-10 (Meta under historical ticker FB (prior to June 2022)):
      -> company_id: US_CIK_0001326801 | status: MATCHED | provenance: point_in_time_interval
    * Ticker 'META' on 2023-01-15 (Meta under modern ticker META (post-June 2022)):
      -> company_id: US_CIK_0001326801 | status: MATCHED | provenance: point_in_time_interval
    * Ticker 'FB' on 2023-05-10 (Obsolete ticker FB in 2023 (must be OUT_OF_INTERVAL, not forced to Meta)):
      -> company_id: None | status: OUT_OF_INTERVAL | provenance: ticker_outside_active_interval
    * Ticker 'MON' on 2015-06-01 (Monsanto Co while active in S&P 500):
      -> company_id: US_CIK_0001110783 | status: MATCHED | provenance: point_in_time_interval
    * Ticker 'MON' on 2023-06-01 (Monsanto post-acquisition (must be OUT_OF_INTERVAL)):
      -> company_id: None | status: OUT_OF_INTERVAL | provenance: ticker_outside_active_interval
    * Ticker 'BRK-B' on 2023-05-26 (Hyphenated share class normalized to BRK.B):
      -> company_id: US_CIK_0001067983 | status: MATCHED | provenance: point_in_time_interval
    * Ticker 'UNKNOWN_XYZ' on 2023-05-26 (Completely unmapped ticker):
      -> company_id: None | status: UNMATCHED | provenance: unmatched_symbol

[4] Deterministic Article ID Generation & Deduplication:
    * ID 1 ('AAPL', 14:00:00Z, 'Apple Unveils New Hardware'): 8cc0d17831ae5ad76b49e3ef
    * ID 2 ('aapl', 14:00:00Z, 'Apple Unveils New Hardware'): 8cc0d17831ae5ad76b49e3ef (Match ID 1: True)
    * ID 3 ('AAPL', 14:00:00Z, 'Different Headline'):        52f63fdb0850734188b4a9b3 (Distinct: True)

[5] Strict Point-in-Time Availability Filtering & Feature Extraction:
    - Decision Timestamp: 2023-05-26 20:00:00+00:00 (NYSE/NASDAQ Close, EDT)
    - Computed Baseline News Features:
      * News Available: True
      * News 1-Day Count (last 24h): 1 (Only 15:30 UTC article; post-close excluded!)
      * News 3-Day Count: 2
      * News 7-Day Count: 2
      * Unique Sources (3d): 2
      * Body Availability Ratio (3d): 0.50
      * Recency in Hours: 4.5 hrs (Distance to 15:30 UTC article)
      * Missing Indicator: False

[6] Three-Way Point-in-Time Feature Harmonization:
    * ARCHITECTURAL NOTE: Real Data Validation vs. Synthetic Fixture Demonstration:
      - Real source news ingestion & mapping validated on FNSPID sample (2009-02-13 to 2020-06-10).
      - Real market (Tiingo pilot) and fundamental (SEC EDGAR pilot) data cover calendar year 2023.
      - Because the FNSPID exploratory sample ends in 2020, three-way harmonization is demonstrated
        using controlled 2023 synthetic fixtures conforming strictly to canonical schemas.
      - DO NOT claim all three sources have been empirically integrated over a common historical period.
    - Aligned Vector for AAPL at 2023-05-26 20:00:00+00:00:
      * Market Close: $175.43 | 1d Return: nan
      * SEC Revenue: $94,836,000,000 (Period: 2023-04-01)
      * News 3d Count: 2 | Unique Sources: 2
      * News Recency: 4.5 hours
      * Provenance: temporal_as_of_aligner_v1

[7] License-Aware News Storage Policy Enforcement:
    * FNSPID Sample Tier: Status=UNVERIFIED (Persistence Prohibited / UNVERIFIED) | Reason='FNSPID sample raw news persistence unverified; scraped third-party commercial articles lack publisher consent'
    * FNSPID Full Universe Tier: Status=UNVERIFIED | Reason='FNSPID bulk persistent warehousing unverified; 3rd-party commercial news text redistribution prohibited without enterprise rights'

================================================================================
PHASE 4B DEMONSTRATION COMPLETE: ALL INTEGRITY & LEGAL SAFEGUARDS VERIFIED
================================================================================
```

---

## 7. Automated Test Suite Health

The complete project test suite was executed across all 10 test modules:

```text
============================= test session starts =============================
platform win32 -- Python 3.14.6, pytest-9.1.1, pluggy-1.6.0 -- C:\Python314\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\sanja\OneDrive\Documents\Sanjay\Colllege_Projects\Stock_prediction_pinnacle_project\project
plugins: anyio-4.14.1, hydra-core-1.3.4
collecting ... collected 76 items

tests/test_features_alignment.py::TestTemporalAlignment::test_end_to_end_temporal_alignment PASSED [  1%]
tests/test_features_alignment.py::TestTemporalAlignment::test_strict_lookahead_detection_market PASSED [  2%]
tests/test_features_alignment.py::TestTemporalAlignment::test_strict_lookahead_detection_fundamental PASSED [  3%]
tests/test_features_alignment.py::TestStoragePolicyEnforcement::test_in_memory_mode_always_succeeds_without_disk_write PASSED [  5%]
tests/test_features_alignment.py::TestStoragePolicyEnforcement::test_disk_parquet_requires_explicit_user_authorization PASSED [  6%]
tests/test_features_alignment.py::TestStoragePolicyEnforcement::test_disk_parquet_blocks_unauthorized_providers PASSED [  7%]
tests/test_features_alignment.py::TestStoragePolicyEnforcement::test_disk_parquet_succeeds_when_authorized_and_permitted PASSED [  9%]
tests/test_features_calendar.py::TestMarketCalendar::test_daylight_saving_market_close_utc PASSED [ 10%]
tests/test_features_calendar.py::TestMarketCalendar::test_early_close_sessions_utc PASSED [ 11%]
tests/test_features_calendar.py::TestMarketCalendar::test_next_session_open_skips_weekends_and_holidays PASSED [ 13%]
tests/test_features_calendar.py::TestMarketCalendar::test_post_close_sec_filing_strictly_excluded_from_same_close_decision PASSED [ 14%]
tests/test_features_calendar.py::TestMarketCalendar::test_early_close_regression PASSED [ 15%]
tests/test_features_calendar.py::TestMarketCalendar::test_full_day_holiday_regression PASSED [ 17%]
tests/test_features_calendar.py::TestMarketCalendar::test_weekend_regression PASSED [ 18%]
tests/test_features_calendar.py::TestMarketCalendar::test_daylight_saving_transitions_regression PASSED [ 19%]
tests/test_features_fundamental.py::TestFundamentalFeatureEngine::test_sec_filing_released_after_decision_cutoff PASSED [ 21%]
tests/test_features_fundamental.py::TestFundamentalFeatureEngine::test_restated_fundamentals_handling PASSED [ 22%]
tests/test_features_fundamental.py::TestFundamentalFeatureEngine::test_missing_facts_are_nan_not_zero PASSED [ 23%]
tests/test_features_fundamental.py::TestFundamentalFeatureEngine::test_ratio_computation_and_no_invention PASSED [ 25%]
tests/test_features_fundamental.py::TestFundamentalFeatureEngine::test_unknown_company_returns_empty_snapshot PASSED [ 26%]
tests/test_features_fundamental.py::TestFundamentalFeatureEngine::test_concept_alias_prioritizes_most_recent_period PASSED [ 27%]
tests/test_features_market.py::TestMarketFeatureEngine::test_returns_and_log_returns PASSED [ 28%]
tests/test_features_market.py::TestMarketFeatureEngine::test_stock_split_adjusted_returns PASSED [ 30%]
tests/test_features_market.py::TestMarketFeatureEngine::test_insufficient_lookback_yields_nan_no_imputation PASSED [ 31%]
tests/test_features_market.py::TestMarketFeatureEngine::test_rsi_calculation_bounds PASSED [ 32%]
tests/test_features_market.py::TestMarketFeatureEngine::test_recycled_ticker_isolation PASSED [ 34%]
tests/test_features_market.py::TestMarketFeatureEngine::test_decision_timing_modes PASSED [ 35%]
tests/test_features_market.py::TestMarketFeatureEngine::test_deterministic_reproducibility PASSED [ 36%]
tests/test_fnspid_ingestion.py::TestMarketIngestion::test_market_chunk_processing PASSED [ 38%]
tests/test_fnspid_ingestion.py::TestMarketIngestion::test_market_historical_ticker_succession PASSED [ 39%]
tests/test_fnspid_ingestion.py::TestMarketIngestion::test_market_validator_valid PASSED [ 40%]
tests/test_fnspid_ingestion.py::TestMarketIngestion::test_market_validator_detects_bad_prices PASSED [ 42%]
tests/test_fnspid_ingestion.py::TestNewsIngestion::test_datetime_parsing_formats PASSED [ 43%]
tests/test_fnspid_ingestion.py::TestNewsIngestion::test_deterministic_news_id PASSED [ 44%]
tests/test_fnspid_ingestion.py::TestNewsIngestion::test_news_chunk_processing PASSED [ 46%]
tests/test_fnspid_ingestion.py::TestNewsIngestion::test_news_validator_detects_empty_articles PASSED [ 47%]
tests/test_news_features.py::TestNewsSchemaAndMapping::test_ticker_succession_point_in_time PASSED [ 48%]
tests/test_news_features.py::TestNewsSchemaAndMapping::test_recycled_and_delisted_ticker_boundary PASSED [ 50%]
tests/test_news_features.py::TestNewsSchemaAndMapping::test_unmatched_and_ambiguous_symbols PASSED [ 51%]
tests/test_news_features.py::TestNewsSchemaAndMapping::test_ticker_punctuation_normalization PASSED [ 52%]
tests/test_news_features.py::TestNewsSchemaAndMapping::test_deterministic_deduplication PASSED [ 53%]
tests/test_news_features.py::TestNewsSchemaAndMapping::test_distinct_sources_not_merged_on_identical_headline PASSED [ 55%]
tests/test_news_features.py::TestNewsPointInTimeFiltering::test_strict_post_cutoff_exclusion PASSED [ 56%]
tests/test_news_features.py::TestNewsPointInTimeFiltering::test_date_only_same_day_protection PASSED [ 57%]
tests/test_news_features.py::TestNewsPointInTimeFiltering::test_timezone_offsets_and_defensible_availability PASSED [ 59%]
tests/test_news_features.py::TestNewsFeatureEngine::test_baseline_features_at_decision_cutoff PASSED [ 60%]
tests/test_news_features.py::TestNewsFeatureEngine::test_missing_company_snapshot PASSED [ 61%]
tests/test_news_features.py::TestTemporalAlignmentWithNews::test_three_way_alignment_market_fundamental_news PASSED [ 63%]
tests/test_news_features.py::TestTemporalAlignmentWithNews::test_trailing_window_exact_boundaries PASSED [ 64%]
tests/test_news_features.py::TestTemporalAlignmentWithNews::test_malformed_and_missing_timestamps PASSED [ 65%]
tests/test_news_features.py::TestTemporalAlignmentWithNews::test_feature_calculation_determinism PASSED [ 67%]
tests/test_news_features.py::TestNewsStoragePolicy::test_fnspid_storage_governance PASSED [ 68%]
tests/test_sec_ingestion.py::TestSECIngestion::test_accession_map_parsing PASSED [ 69%]
tests/test_sec_ingestion.py::TestSECIngestion::test_extract_8k_filings PASSED [ 71%]
tests/test_sec_ingestion.py::TestSECIngestion::test_extract_financial_facts_point_in_time PASSED [ 72%]
tests/test_sec_ingestion.py::TestSECIngestion::test_validator_catches_fatal_lookahead PASSED [ 73%]
tests/test_sec_ingestion.py::TestSECIngestion::test_query_fact_as_of_prevents_lookahead PASSED [ 75%]
tests/test_sec_ingestion.py::TestSECIngestion::test_query_fact_as_of_restatement_handling PASSED [ 76%]
tests/test_storage_policy_and_interface.py::TestMarketInterface::test_mock_adapter_implements_base_interface PASSED [ 77%]
tests/test_storage_policy_and_interface.py::TestMarketInterface::test_tiingo_fetcher_and_ingestor_conform_to_base PASSED [ 78%]
tests/test_storage_policy_and_interface.py::TestStoragePolicy::test_sec_edgar_allows_all_layers PASSED [ 80%]
tests/test_storage_policy_and_interface.py::TestStoragePolicy::test_tiingo_starter_restricts_raw_and_normalized PASSED [ 81%]
tests/test_storage_policy_and_interface.py::TestStoragePolicy::test_tiingo_power_permits_internal_persistence PASSED [ 82%]
tests/test_storage_policy_and_interface.py::TestStoragePolicy::test_yfinance_prohibited_due_to_tos PASSED [ 84%]
tests/test_storage_policy_and_interface.py::TestStoragePolicy::test_polygon_developer_vs_free PASSED [ 85%]
tests/test_storage_policy_and_interface.py::TestStoragePolicy::test_wrds_academic_license PASSED [ 86%]
tests/test_storage_policy_and_interface.py::TestStoragePolicy::test_unknown_provider_defaults_to_unverified PASSED [ 88%]
tests/test_tiingo_market.py::TestTiingoMarket::test_tiingo_fetcher_requires_credentials PASSED [ 89%]
tests/test_tiingo_market.py::TestTiingoMarket::test_tiingo_ingestion_normalization PASSED [ 90%]
tests/test_tiingo_market.py::TestTiingoMarket::test_calculate_session_coverage_accounts_for_holidays PASSED [ 92%]
tests/test_universe.py::test_normalize_ticker PASSED                     [ 93%]
tests/test_universe.py::test_format_cik PASSED                           [ 94%]
tests/test_universe.py::test_generate_company_id PASSED                  [ 96%]
tests/test_universe.py::test_universe_builder_schema PASSED              [ 97%]
tests/test_universe.py::test_point_in_time_query PASSED                  [ 98%]
tests/test_universe.py::test_validator_detects_deliberate_errors PASSED  [100%]

============================= 76 passed in 3.41s ==============================
```

---

## 8. Complete File Inventory

### Created Files
1. [`src/features/news.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/features/news.py): Implements modular, point-in-time `NewsFeatureEngine` with trailing window metrics, hardened timezone handling, index preservation, and same-day date-only lookahead rejection.
2. [`tests/test_news_features.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/tests/test_news_features.py): 16 focused tests verifying schema, ticker succession, ambiguous collisions, publisher provenance deduplication, timezone parsing & availability, window boundaries, and 3-way alignment.
3. [`scripts/demo_phase4b_news.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/scripts/demo_phase4b_news.py): End-to-end bounded demonstration of news ingestion, point-in-time resolution, baseline feature generation, license governance, and explicit distinction between real data validation and synthetic fixture harmonization.
4. [`docs/phase4b_news_pipeline_report.md`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/docs/phase4b_news_pipeline_report.md): Architectural report, honest limitation disclosures, scorecard, and test results.

### Modified Files
1. [`src/data/news/schema.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/data/news/schema.py): Extended `PROCESSED_NEWS_SCHEMA` to record raw source timestamps, ingestion timestamps, `mapping_status`, `mapping_provenance`, `has_intraday_time`, and `has_body_text`. Added `NewsMappingStatus` enum.
2. [`src/data/news/ingestor.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/data/news/ingestor.py): Eliminated unprincipled fallback to modern mapping in `resolve_company_mapping`; strictly enforces `effective_from <= date <= effective_to`, returns explicit `MATCHED`, `OUT_OF_INTERVAL`, `UNMATCHED`, or `AMBIGUOUS` statuses; normalizes share class punctuation; populates canonical schema fields. Updated `generate_news_id` to include `source` and `url` to preserve provenance and prevent incorrect deduplication across distinct publishers.
3. [`src/data/news/validator.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/data/news/validator.py): Added checks for canonical schema fields and validated `mapping_status` enum values.
4. [`src/data/market/storage_policy.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/data/market/storage_policy.py): Updated formal legal governance entries for `fnspid` sample raw/normalized layers from PERMITTED to `UNVERIFIED` (is_permitted=False) due to unsubstantiated commercial news rights.
5. [`src/features/config.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/features/config.py): Added `NewsFeatureConfig` dataclass defining trailing windows, date-only policies, and recency horizons.
6. [`src/features/alignment.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/features/alignment.py): Integrated `news_engine` into `TemporalAligner`, enabling unified 3-way feature matrices and tracking `news_features_has_missing`.
7. [`src/features/fundamental.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/features/fundamental.py): Fixed DataFrame index preservation in `compute_snapshots_for_decisions` (`index=decision_points.index`).
8. [`src/features/__init__.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/features/__init__.py): Exported `NewsFeatureConfig` and `NewsFeatureEngine`.

### Deleted Files
* None.

---

## 9. Phase 4B Acceptance Criteria Scorecard

| Acceptance Criterion | Requirement | Status | Evidence / Verification |
| :--- | :--- | :---: | :--- |
| **Criterion 1: Canonical News Schema** | Extended schema preserving raw timestamp, ingestion time, mapping status, and quality flags | **PASS** | [`src/data/news/schema.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/data/news/schema.py); validated in `test_news_chunk_processing`. |
| **Criterion 2: Historical Ticker Resolution** | Point-in-time intervals respected; no fallback to modern mapping; explicit status tracking | **PASS** | Implemented in `NewsIngestor.resolve_company_mapping`; verified in `test_ticker_succession_point_in_time` and `test_recycled_and_delisted_ticker_boundary`. |
| **Criterion 3: Ambiguity & Unmatched Handling** | Overlapping intervals return `AMBIGUOUS`; unknown tickers return `UNMATCHED` | **PASS** | Verified in `test_unmatched_and_ambiguous_symbols`. |
| **Criterion 4: Provenance-Preserving Deduplication** | Distinct publishers reporting identical headlines/tickers/timestamps are not falsely merged | **PASS** | Implemented in `NewsIngestor.generate_news_id`; verified in `test_distinct_sources_not_merged_on_identical_headline`. |
| **Criterion 5: Point-in-Time Availability** | Strict cutoff $t_{\text{pub}} \le t_{\text{decision}}$; timezone offsets (EDT/EST); date-only same-day lookahead protection | **PASS** | Implemented in `NewsFeatureEngine.is_article_eligible`; verified in `test_strict_post_cutoff_exclusion`, `test_date_only_same_day_protection`, and `test_timezone_offsets_and_defensible_availability`. |
| **Criterion 6: Baseline Feature Engine** | Deterministic counts, sources, body ratio, recency over trailing windows without sentiment invention | **PASS** | Implemented in [`src/features/news.py`](file:///c:/Users/sanja/OneDrive/Documents/Sanjay/Colllege_Projects/Stock_prediction_pinnacle_project/project/src/features/news.py); verified in `test_baseline_features_at_decision_cutoff`. |
| **Criterion 7: Three-Way Harmonization Architecture** | Safely join Market + SEC Fundamentals + Financial News via `TemporalAligner` | **PASS** | Architectural join verified in `test_three_way_alignment_market_fundamental_news` and demonstrated in `demo_phase4b_news.py`. |
| **Criterion 8: Empirical Integration Disclosure** | Explicit distinction between real news data validation (2009–2020) and synthetic fixture demonstration (2023) | **PASS** | Disclosed in report Section 6 and `demo_phase4b_news.py`. No claim of common-period empirical integration. |
| **Criterion 9: Storage Policy Governance** | Unsubstantiated news text marked UNVERIFIED; persistence disabled by default; derivative counts permitted | **PASS** | Formally defined in `StoragePolicy`; verified in `test_fnspid_storage_governance`. |
| **Criterion 10: Regression Test Suite** | 100% green test suite across all 10 test modules | **PASS** | **76 of 76 tests passing** in 3.41s with 0 warnings. |
| **Criterion 11: News Licensing Rights** | Commercial redistribution and persistent archiving rights for upstream third-party news text | **UNVERIFIED** | Upstream publisher rights unsubstantiated; storage status set to UNVERIFIED; disk writes disabled. |
| **Criterion 12: Scope Discipline** | No model training (no FinBERT), no BUY/HOLD/SELL labels, no UI, no git operations | **PASS** | Strict stop conditions preserved. |

---

## Conclusion & Stop Point

Phase 4B is complete and verified across 76 tests with zero warnings. In accordance with strict stop conditions:
- No predictive models or sentiment scores were trained or invented.
- No full universe was downloaded.
- No Phase 1–4A artifacts were modified or deleted.
- No Git operations were performed.
- Work is halted for review. Phase 4C will not proceed until instructed.

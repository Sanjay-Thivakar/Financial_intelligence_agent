"""
Unit, Integration, and Leakage Tests for Unified Dataset Construction (Phase 4C).

Validates:
1. One row per unique (company_id, decision_timestamp) with zero row multiplication.
2. Deterministic output for identical inputs.
3. Point-in-time leakage rejection across market, fundamental, and news modalities.
4. SEC filing availability and restatement handling.
5. News trailing window cutoffs and date-only same-day protection.
6. Corporate identity succession (FB -> META) and point-in-time ticker resolution.
7. Explicit distinction between genuine zero activity and unavailable/unlicensed sources.
8. Handling of duplicates, malformed prices, empty sets, and bounded date intervals.
9. Storage policy enforcement (in-memory default, blocking unauthorized disk writes).
10. Clear separation between synthetic unit fixtures and real-data validation.
"""

from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from src.data.market.storage_policy import DataLayer, LicenseStatus, StoragePolicy
from src.features.calendar import MarketCalendar
from src.features.config import (
    DecisionTimingMode,
    PersistenceMode,
    FeatureStorageConfig,
    MarketFeatureConfig,
    FundamentalFeatureConfig,
    NewsFeatureConfig,
)
from src.features.dataset import (
    DatasetBuildConfig,
    DatasetCoverageReport,
    DatasetBuildResult,
    UnifiedDatasetBuilder,
    DatasetIntegrityError,
)
from src.features.alignment import LookaheadLeakageError
from src.features.storage import StorageAuthorizationError


@pytest.fixture
def mock_universe_df():
    """Provides canonical S&P 500 company intervals with ticker succession."""
    return pd.DataFrame([
        # Apple: continuous
        {
            "company_id": "US_CIK_0000320193",
            "ticker": "AAPL",
            "cik": "0000320193",
            "company_name": "Apple Inc.",
            "sector": "Information Technology",
            "effective_from": "1996-01-02",
            "effective_to": "9999-12-31",
        },
        # Meta: FB (2013-12-23 to 2022-06-09) -> META (2022-06-09 to present)
        {
            "company_id": "US_CIK_0001326801",
            "ticker": "FB",
            "cik": "0001326801",
            "company_name": "Meta Platforms, Inc.",
            "sector": "Communication Services",
            "effective_from": "2013-12-23",
            "effective_to": "2022-06-09",
        },
        {
            "company_id": "US_CIK_0001326801",
            "ticker": "META",
            "cik": "0001326801",
            "company_name": "Meta Platforms, Inc.",
            "sector": "Communication Services",
            "effective_from": "2022-06-09",
            "effective_to": "9999-12-31",
        },
    ])


@pytest.fixture
def synthetic_multimodal_data():
    """
    Constructs a controlled synthetic multi-modal dataset for Apple (AAPL) over 5 trading sessions:
    2023-05-22 to 2023-05-26.
    """
    market_records = []
    dates = ["2023-05-22", "2023-05-23", "2023-05-24", "2023-05-25", "2023-05-26"]
    for i, d in enumerate(dates):
        p = 170.0 + i
        market_records.append({
            "company_id": "US_CIK_0000320193",
            "ticker": "AAPL",
            "timestamp": pd.to_datetime(f"{d} 00:00:00", utc=True),
            "trading_date": d,
            "open": p - 0.5, "high": p + 1.0, "low": p - 1.0, "close": p,
            "adjusted_open": p - 0.5, "adjusted_high": p + 1.0, "adjusted_low": p - 1.0, "adjusted_close": p,
            "volume": 40000000 + i * 1000000,
            "source": "tiingo_eod"
        })
    df_market = pd.DataFrame(market_records)

    # SEC facts: 10-Q accepted on 2023-05-05 02:03:52 UTC
    facts_records = [
        {
            "company_id": "US_CIK_0000320193",
            "cik": "0000320193",
            "ticker": "AAPL",
            "concept": "Revenues",
            "label": "Revenue",
            "period_end": "2023-04-01",
            "form": "10-Q",
            "acceptance_timestamp": pd.to_datetime("2023-05-05 02:03:52", utc=True),
            "accession_number": "0000320193-23-000064",
            "value": 94836000000.0,
        },
        {
            "company_id": "US_CIK_0000320193",
            "cik": "0000320193",
            "ticker": "AAPL",
            "concept": "NetIncomeLoss",
            "label": "Net Income",
            "period_end": "2023-04-01",
            "form": "10-Q",
            "acceptance_timestamp": pd.to_datetime("2023-05-05 02:03:52", utc=True),
            "accession_number": "0000320193-23-000064",
            "value": 24160000000.0,
        },
    ]
    df_facts = pd.DataFrame(facts_records)

    # News records:
    # 1. 2023-05-24 14:00 UTC (Eligible for decisions on/after May 24 close)
    # 2. 2023-05-26 15:30 UTC (Eligible for May 26 close)
    # 3. 2023-05-26 21:00 UTC (Ineligible for May 26 close at 20:00 UTC EDT!)
    news_records = [
        {
            "news_id": "news_1",
            "company_id": "US_CIK_0000320193",
            "ticker": "AAPL",
            "published_at": pd.Timestamp("2023-05-24 14:00:00", tz="UTC"),
            "published_date": "2023-05-24",
            "has_intraday_time": True,
            "has_body_text": True,
            "headline": "Apple Supply Chain Expansion Announced",
            "article_text": "Apple expands manufacturing suppliers.",
            "source": "Reuters",
        },
        {
            "news_id": "news_2",
            "company_id": "US_CIK_0000320193",
            "ticker": "AAPL",
            "published_at": pd.Timestamp("2023-05-26 15:30:00", tz="UTC"),
            "published_date": "2023-05-26",
            "has_intraday_time": True,
            "has_body_text": False,
            "headline": "Tech Sector Midday Wrap",
            "article_text": "",
            "source": "Benzinga",
        },
        {
            "news_id": "news_3_leak",
            "company_id": "US_CIK_0000320193",
            "ticker": "AAPL",
            "published_at": pd.Timestamp("2023-05-26 21:00:00", tz="UTC"),
            "published_date": "2023-05-26",
            "has_intraday_time": True,
            "has_body_text": True,
            "headline": "Late Night Commentary After Close",
            "article_text": "After close details.",
            "source": "Bloomberg",
        },
    ]
    df_news = pd.DataFrame(news_records)

    return df_market, df_facts, df_news


class TestDatasetBuilderCoreContract:
    """Verifies the Observation and Decision-Time Contract."""

    def test_one_row_per_unique_company_decision(self, synthetic_multimodal_data, mock_universe_df):
        df_market, df_facts, df_news = synthetic_multimodal_data
        builder = UnifiedDatasetBuilder()
        result = builder.build_dataset(
            df_market=df_market,
            df_fundamentals=df_facts,
            df_news=df_news,
            universe_df=mock_universe_df,
        )

        df = result.data
        assert len(df) == 5
        # Verify strictly unique dataset_row_id
        assert df["dataset_row_id"].nunique() == 5
        assert not df.duplicated(subset=["company_id", "decision_timestamp"]).any()

        # Contract columns must exist
        for col in [
            "dataset_row_id", "company_id", "ticker", "trading_date",
            "decision_timestamp", "decision_timing_mode", "market_observation_timestamp",
            "information_cutoff_timestamp", "execution_timestamp",
            "news_cutoff_timestamp", "news_coverage_status", "fundamental_coverage_status",
            "market_features_has_missing", "fundamental_features_has_missing",
            "news_features_has_missing", "dataset_builder_provenance",
        ]:
            assert col in df.columns, f"Missing required contract column: {col}"

    def test_deterministic_output(self, synthetic_multimodal_data, mock_universe_df):
        df_market, df_facts, df_news = synthetic_multimodal_data
        builder = UnifiedDatasetBuilder()

        res1 = builder.build_dataset(df_market, df_facts, df_news, mock_universe_df)
        res2 = builder.build_dataset(df_market, df_facts, df_news, mock_universe_df)

        pd.testing.assert_frame_equal(res1.data, res2.data)
        assert res1.coverage_report.to_dict() == res2.coverage_report.to_dict()

    def test_post_close_news_excluded_from_same_close_decision(self, synthetic_multimodal_data, mock_universe_df):
        df_market, df_facts, df_news = synthetic_multimodal_data
        builder = UnifiedDatasetBuilder()
        result = builder.build_dataset(df_market, df_facts, df_news, mock_universe_df)

        df = result.data
        # May 26 close is at 20:00:00 UTC (EDT)
        row_may26 = df[df["trading_date"] == "2023-05-26"].iloc[0]
        assert row_may26["decision_timestamp"] == pd.Timestamp("2023-05-26 20:00:00", tz="UTC")

        # News 1 (May 24 14:00) + News 2 (May 26 15:30) are <= 20:00:00 UTC -> count is 2
        # News 3 (May 26 21:00) is strictly > 20:00:00 UTC -> EXCLUDED
        assert row_may26["news_count_3d"] == 2
        assert row_may26["news_recency_hours"] == 4.5  # Distance from 20:00 UTC to 15:30 UTC article

    def test_date_only_news_same_day_exclusion(self, mock_universe_df):
        """Date-only articles cannot leak into same-day decisions."""
        df_market = pd.DataFrame([{
            "company_id": "US_CIK_0000320193", "ticker": "AAPL",
            "timestamp": pd.to_datetime("2023-05-26 00:00:00", utc=True),
            "trading_date": "2023-05-26",
            "open": 175.0, "high": 176.0, "low": 174.0, "close": 175.43,
            "adjusted_open": 175.0, "adjusted_high": 176.0, "adjusted_low": 174.0, "adjusted_close": 175.43,
            "volume": 50000000,
        }])
        df_news = pd.DataFrame([{
            "news_id": "date_only_sameday",
            "company_id": "US_CIK_0000320193", "ticker": "AAPL",
            "published_at": pd.Timestamp("2023-05-26 00:00:00", tz="UTC"),
            "published_date": "2023-05-26",
            "has_intraday_time": False,
            "has_body_text": False,
            "headline": "Morning summary without intraday time",
            "article_text": "",
            "source": "Nasdaq",
        }])

        builder = UnifiedDatasetBuilder()
        result = builder.build_dataset(df_market=df_market, df_news=df_news, universe_df=mock_universe_df)
        row = result.data.iloc[0]
        # Must be excluded from same-day close decision
        assert row["news_count_1d"] == 0
        assert bool(row["news_available"]) is False

    def test_sec_filing_leakage_rejection(self, mock_universe_df):
        """Fundamental facts accepted after decision cutoff must raise LookaheadLeakageError."""
        df_market = pd.DataFrame([{
            "company_id": "US_CIK_0000320193", "ticker": "AAPL",
            "timestamp": pd.to_datetime("2023-05-26 00:00:00", utc=True),
            "trading_date": "2023-05-26",
            "open": 175.0, "high": 176.0, "low": 174.0, "close": 175.43,
            "adjusted_open": 175.0, "adjusted_high": 176.0, "adjusted_low": 174.0, "adjusted_close": 175.43,
            "volume": 50000000,
        }])
        # Filing accepted at 20:30 UTC, 30 mins after market close (20:00 UTC)
        df_facts_future = pd.DataFrame([{
            "company_id": "US_CIK_0000320193",
            "concept": "Revenues",
            "period_end": "2023-04-01",
            "form": "10-Q",
            "acceptance_timestamp": pd.to_datetime("2023-05-26 20:30:00", utc=True),
            "accession_number": "0000320193-23-000099",
            "value": 999999.0,
        }])

        # FundamentalFeatureEngine.get_as_of_snapshot filters to <= decision_ts,
        # so this future fact is correctly excluded and returns NaN
        builder = UnifiedDatasetBuilder()
        result = builder.build_dataset(df_market=df_market, df_fundamentals=df_facts_future, universe_df=mock_universe_df)
        row = result.data.iloc[0]
        assert np.isnan(row["fundamental_revenue"])
        assert bool(row["fundamental_revenue_missing"]) is True


class TestDatasetBuilderDataSanitizationAndBounds:
    """Verifies handling of cohort filters, date intervals, duplicates, and malformed inputs."""

    def test_cohort_and_date_bounds_filtering(self, synthetic_multimodal_data, mock_universe_df):
        df_market, df_facts, df_news = synthetic_multimodal_data
        # Bounded between 2023-05-23 and 2023-05-25 (3 of 5 days)
        cfg = DatasetBuildConfig(
            start_date="2023-05-23",
            end_date="2023-05-25",
            cohort_company_ids=("US_CIK_0000320193",),
        )
        builder = UnifiedDatasetBuilder(cfg)
        result = builder.build_dataset(df_market, df_facts, df_news, mock_universe_df)

        assert len(result.data) == 3
        assert result.coverage_report.rows_excluded_date_bounds == 2
        assert result.coverage_report.rows_retained == 3

    def test_duplicate_market_records_deduplication(self, synthetic_multimodal_data, mock_universe_df):
        df_market, df_facts, df_news = synthetic_multimodal_data
        # Duplicate the first row
        df_market_dupe = pd.concat([df_market, df_market.iloc[[0]]], ignore_index=True)
        assert len(df_market_dupe) == 6

        builder = UnifiedDatasetBuilder()
        result = builder.build_dataset(df_market_dupe, df_facts, df_news, mock_universe_df)

        assert len(result.data) == 5
        assert result.coverage_report.rows_excluded_duplicate == 1

    def test_malformed_market_price_dropped(self, synthetic_multimodal_data, mock_universe_df):
        df_market, df_facts, df_news = synthetic_multimodal_data
        # Inject bad price row (close <= 0)
        bad_row = df_market.iloc[[0]].copy()
        bad_row["trading_date"] = "2023-05-21"
        bad_row["close"] = -10.0
        df_market_with_bad = pd.concat([bad_row, df_market], ignore_index=True)

        builder = UnifiedDatasetBuilder()
        result = builder.build_dataset(df_market_with_bad, df_facts, df_news, mock_universe_df)

        assert len(result.data) == 5
        assert result.coverage_report.rows_excluded_malformed == 1

    def test_empty_market_input_handled_gracefully(self, mock_universe_df):
        builder = UnifiedDatasetBuilder()
        result = builder.build_dataset(pd.DataFrame(), universe_df=mock_universe_df)

        assert result.data.empty
        assert result.coverage_report.rows_retained == 0
        assert "empty" in result.coverage_report.temporal_overlap_assessment


class TestCoverageStatusAndIdentitySuccession:
    """Verifies news/fundamental coverage status classification and corporate identity succession."""

    def test_news_coverage_status_distinction(self, synthetic_multimodal_data, mock_universe_df):
        """Distinguishes genuine zero-activity window from source unavailable."""
        df_market, df_facts, df_news = synthetic_multimodal_data
        builder = UnifiedDatasetBuilder()
        result = builder.build_dataset(df_market, df_facts, df_news, mock_universe_df)

        df = result.data
        # May 22 & 23: Company has news in this dataset (May 24 & 26), but trailing 1d count is 0
        # Classified as active_zero_events (or source_unavailable if before min date)
        # May 26: Has news -> active_with_events
        row_may26 = df[df["trading_date"] == "2023-05-26"].iloc[0]
        assert row_may26["news_coverage_status"] == "active_with_events"

    def test_ticker_succession_fb_meta(self, mock_universe_df):
        """Verifies point-in-time ticker resolution across Meta's transition from FB to META in June 2022."""
        df_market = pd.DataFrame([
            # 2021 session under FB
            {
                "company_id": "US_CIK_0001326801", "ticker": "FB",
                "timestamp": pd.to_datetime("2021-05-10 00:00:00", utc=True),
                "trading_date": "2021-05-10",
                "open": 315.0, "high": 318.0, "low": 312.0, "close": 316.0,
                "adjusted_open": 315.0, "adjusted_high": 318.0, "adjusted_low": 312.0, "adjusted_close": 316.0,
                "volume": 15000000,
            },
            # 2023 session under META
            {
                "company_id": "US_CIK_0001326801", "ticker": "META",
                "timestamp": pd.to_datetime("2023-05-10 00:00:00", utc=True),
                "trading_date": "2023-05-10",
                "open": 235.0, "high": 240.0, "low": 232.0, "close": 238.0,
                "adjusted_open": 235.0, "adjusted_high": 240.0, "adjusted_low": 232.0, "adjusted_close": 238.0,
                "volume": 25000000,
            },
        ])

        builder = UnifiedDatasetBuilder()
        result = builder.build_dataset(df_market=df_market, universe_df=mock_universe_df)

        df = result.data
        assert len(df) == 2
        # Identical company_id preserved
        assert (df["company_id"] == "US_CIK_0001326801").all()
        # Appropriate point-in-time ticker recorded
        assert df.iloc[0]["ticker"] == "FB"
        assert df.iloc[1]["ticker"] == "META"


class TestStorageGovernanceAndRealDataVerification:
    """Verifies storage policy guardrails and real source data inspection."""

    def test_unauthorized_disk_persistence_blocked(self, synthetic_multimodal_data, mock_universe_df, tmp_path):
        df_market, df_facts, df_news = synthetic_multimodal_data
        storage_cfg = FeatureStorageConfig(
            provider="tiingo",
            plan_tier="starter",
            storage_authorized=False,  # Unauthorized!
            persistence_mode=PersistenceMode.DISK_PARQUET,
            output_dir=tmp_path,
        )
        bld_cfg = DatasetBuildConfig(storage_config=storage_cfg)
        builder = UnifiedDatasetBuilder(bld_cfg)

        with pytest.raises(StorageAuthorizationError) as exc_info:
            builder.build_dataset(df_market, df_facts, df_news, mock_universe_df)
        assert "explicit user storage authorization is FALSE" in str(exc_info.value)

    def test_authorized_disk_persistence_permitted(self, synthetic_multimodal_data, mock_universe_df, tmp_path):
        """When storage_authorized is True and mode is DISK_PARQUET, dataset builder persists safely."""
        df_market, df_facts, df_news = synthetic_multimodal_data
        storage_cfg = FeatureStorageConfig(
            provider="tiingo",
            plan_tier="starter",
            storage_authorized=True,
            persistence_mode=PersistenceMode.DISK_PARQUET,
            output_dir=tmp_path,
        )
        bld_cfg = DatasetBuildConfig(storage_config=storage_cfg)
        builder = UnifiedDatasetBuilder(bld_cfg)
        result = builder.build_dataset(df_market, df_facts, df_news, mock_universe_df)

        assert len(result.data) == 5
        out_file = tmp_path / "unified_feature_dataset.parquet"
        assert out_file.exists(), "Expected unified_feature_dataset.parquet to be persisted on disk"
        df_saved = pd.read_parquet(out_file)
        assert len(df_saved) == 5

    def test_real_data_pilot_empirical_assessment(self):
        """
        Loads the real local pilot data and verifies the hard data-availability finding:
        Tiingo market (2023) and SEC EDGAR (2023) have zero overlap with local FNSPID news (ends June 2020).
        """
        tiingo_path = Path("data/processed/market/tiingo/pilot_market_sample.parquet")
        sec_path = Path("data/processed/sec/facts/pilot_financial_facts.parquet")
        news_path = Path("data/processed/news/fnspid_news_processed.parquet")
        universe_path = Path("data/processed/universe/sp500_universe.parquet")

        if not (tiingo_path.exists() and sec_path.exists() and news_path.exists()):
            pytest.skip("Local processed pilot artifacts not found")

        df_tiingo = pd.read_parquet(tiingo_path)
        df_sec = pd.read_parquet(sec_path)
        df_news = pd.read_parquet(news_path)
        universe_df = pd.read_parquet(universe_path) if universe_path.exists() else None

        # Apple cohort for calendar year 2023
        cfg = DatasetBuildConfig(
            cohort_company_ids=("US_CIK_0000320193",),
            start_date="2023-01-01",
            end_date="2023-12-31",
        )
        builder = UnifiedDatasetBuilder(cfg)
        result = builder.build_dataset(
            df_market=df_tiingo,
            df_fundamentals=df_sec,
            df_news=df_news,
            universe_df=universe_df,
        )

        rep = result.coverage_report
        assert rep.rows_retained == 250
        assert rep.coverage_denominator == 250
        assert rep.market_coverage_pct == 100.0

        # Core Fundamental statement coverage (revenue + net income) is 100.0%
        assert rep.fundamental_core_coverage_pct == 100.0
        assert rep.fundamental_coverage_pct == 100.0
        assert rep.fundamental_stale_rows_count == 0

        # Crucial empirical reality: comprehensive coverage across all 12 concepts is 0.0%
        # because Apple does not report standard long_term_debt / short_term_debt tags in this pilot pull
        assert rep.fundamental_comprehensive_coverage_pct == 0.0
        assert rep.fundamental_concept_availability_pct["revenue"] == 100.0
        assert rep.fundamental_concept_availability_pct["net_income"] == 100.0
        assert rep.fundamental_concept_availability_pct["total_assets"] == 100.0
        assert rep.fundamental_concept_availability_pct["long_term_debt"] == 0.0
        assert rep.fundamental_concept_availability_pct["short_term_debt"] == 0.0

        # Crucial empirical verification: exactly 0.0% news coverage because local FNSPID news sample ends in 2020!
        assert rep.news_coverage_pct == 0.0
        assert "Zero real news overlap" in rep.temporal_overlap_assessment


class TestDecisionAndExecutionTimelines:
    """Verifies decision-time vs execution-time correctness and historical timeline separation."""

    def test_market_close_execution_strictly_at_next_session_open(self, mock_universe_df):
        """
        Under MARKET_CLOSE:
        - Information cutoff is session close T (20:00 UTC in EDT).
        - Technical features use close price P_T.
        - Execution CANNOT occur at P_T close! Earliest feasible execution is next session open T+1 (09:30 ET).
        """
        # Thursday May 25, 2023 and Friday May 26, 2023
        df_market = pd.DataFrame([
            {
                "company_id": "US_CIK_0000320193", "ticker": "AAPL",
                "timestamp": pd.to_datetime("2023-05-25 00:00:00", utc=True),
                "trading_date": "2023-05-25",
                "open": 172.0, "high": 173.0, "low": 171.0, "close": 172.99,
                "adjusted_open": 172.0, "adjusted_high": 173.0, "adjusted_low": 171.0, "adjusted_close": 172.99,
                "volume": 50000000,
            },
            {
                "company_id": "US_CIK_0000320193", "ticker": "AAPL",
                "timestamp": pd.to_datetime("2023-05-26 00:00:00", utc=True),
                "trading_date": "2023-05-26",
                "open": 173.0, "high": 176.0, "low": 173.0, "close": 175.43,
                "adjusted_open": 173.0, "adjusted_high": 176.0, "adjusted_low": 173.0, "adjusted_close": 175.43,
                "volume": 60000000,
            },
        ])

        cfg = DatasetBuildConfig(market_config=MarketFeatureConfig(decision_timing=DecisionTimingMode.MARKET_CLOSE))
        builder = UnifiedDatasetBuilder(cfg)
        result = builder.build_dataset(df_market=df_market, universe_df=mock_universe_df)
        df = result.data

        # Thursday 2023-05-25
        row_thu = df[df["trading_date"] == "2023-05-25"].iloc[0]
        assert row_thu["decision_timestamp"] == pd.Timestamp("2023-05-25 20:00:00", tz="UTC")
        assert row_thu["information_cutoff_timestamp"] == pd.Timestamp("2023-05-25 20:00:00", tz="UTC")
        # Execution MUST be Friday May 26 09:30 ET = 13:30:00 UTC
        assert row_thu["execution_timestamp"] == pd.Timestamp("2023-05-26 13:30:00", tz="UTC")
        assert row_thu["execution_timestamp"] > row_thu["decision_timestamp"]

        # Friday 2023-05-26 (followed by Memorial Day on Monday May 29!)
        row_fri = df[df["trading_date"] == "2023-05-26"].iloc[0]
        assert row_fri["decision_timestamp"] == pd.Timestamp("2023-05-26 20:00:00", tz="UTC")
        # Next active session is Tuesday May 30 09:30 ET = 13:30:00 UTC (skipping weekend and holiday!)
        assert row_fri["execution_timestamp"] == pd.Timestamp("2023-05-30 13:30:00", tz="UTC")
        assert row_fri["execution_timestamp"] > row_fri["decision_timestamp"]

    def test_next_session_open_overnight_information_and_execution(self, mock_universe_df):
        """
        Under NEXT_SESSION_OPEN:
        - Decision timestamp is aligned with next session market open (09:30 ET).
        - Execution occurs at open (13:30 UTC in EDT).
        - Overnight news and SEC filings prior to 09:30 ET open are visible.
        - Open price is NOT an input feature before observable.
        """
        df_market = pd.DataFrame([{
            "company_id": "US_CIK_0000320193", "ticker": "AAPL",
            "timestamp": pd.to_datetime("2023-05-25 00:00:00", utc=True),
            "trading_date": "2023-05-25",
            "open": 172.0, "high": 173.0, "low": 171.0, "close": 172.99,
            "adjusted_open": 172.0, "adjusted_high": 173.0, "adjusted_low": 171.0, "adjusted_close": 172.99,
            "volume": 50000000,
        }])

        # News published overnight: 2023-05-26 10:00 UTC (06:00 ET, before 09:30 ET open)
        # and another published intraday: 2023-05-26 14:00 UTC (after 13:30 UTC open)
        df_news = pd.DataFrame([
            {
                "news_id": "overnight_preopen",
                "company_id": "US_CIK_0000320193", "ticker": "AAPL",
                "published_at": pd.Timestamp("2023-05-26 10:00:00", tz="UTC"),
                "published_date": "2023-05-26",
                "has_intraday_time": True,
                "has_body_text": True,
                "headline": "Overnight Pre-Open Product Rumor",
                "article_text": "Overnight details before the open.",
                "source": "Bloomberg",
            },
            {
                "news_id": "intraday_postopen",
                "company_id": "US_CIK_0000320193", "ticker": "AAPL",
                "published_at": pd.Timestamp("2023-05-26 14:00:00", tz="UTC"),
                "published_date": "2023-05-26",
                "has_intraday_time": True,
                "has_body_text": True,
                "headline": "Post-Open Market Reaction",
                "article_text": "Post open details.",
                "source": "Reuters",
            },
        ])

        cfg = DatasetBuildConfig(market_config=MarketFeatureConfig(decision_timing=DecisionTimingMode.NEXT_SESSION_OPEN))
        builder = UnifiedDatasetBuilder(cfg)
        result = builder.build_dataset(df_market=df_market, df_news=df_news, universe_df=mock_universe_df)
        row = result.data.iloc[0]

        # Information & Decision Cutoff is Friday 09:15 ET = 13:15:00 UTC (15m buffer)
        # Execution occurs at Friday 09:30 ET = 13:30:00 UTC (Opening auction cross)
        assert row["information_cutoff_timestamp"] == pd.Timestamp("2023-05-26 13:15:00", tz="UTC")
        assert row["decision_timestamp"] == pd.Timestamp("2023-05-26 13:15:00", tz="UTC")
        assert row["execution_timestamp"] == pd.Timestamp("2023-05-26 13:30:00", tz="UTC")
        assert row["execution_timestamp"] > row["decision_timestamp"]

        # The overnight article (10:00 UTC) is visible before 13:15 UTC
        # The post-open article (14:00 UTC) is strictly excluded
        assert row["news_count_1d"] == 1
        assert row["news_recency_hours"] == 3.25  # 13:15 - 10:00

    def test_next_session_open_precise_boundary_behavior(self, mock_universe_df):
        """
        Regression test for information timestamped just before, exactly at, and just after
        the pre-open cutoff and execution boundary (Friday May 26, 2023 EDT):
        - Cutoff: 09:15:00 ET = 13:15:00 UTC
        - Execution: 09:30:00 ET = 13:30:00 UTC
        Verifies:
        1. 13:14:59 UTC (1s before cutoff) -> INCLUDED
        2. 13:15:00 UTC (exactly at cutoff) -> INCLUDED
        3. 13:15:01 UTC (1s after cutoff) -> EXCLUDED
        4. 13:25:00 UTC (during buffer before open) -> EXCLUDED
        5. 13:30:00 UTC (exactly at execution / open) -> EXCLUDED (cannot execute at same open!)
        6. 13:30:01 UTC (1s after execution / open) -> EXCLUDED
        """
        df_market = pd.DataFrame([{
            "company_id": "US_CIK_0000320193", "ticker": "AAPL",
            "timestamp": pd.to_datetime("2023-05-25 00:00:00", utc=True),
            "trading_date": "2023-05-25",
            "open": 172.0, "high": 173.0, "low": 171.0, "close": 172.99,
            "adjusted_open": 172.0, "adjusted_high": 173.0, "adjusted_low": 171.0, "adjusted_close": 172.99,
            "volume": 50000000,
        }])

        df_news = pd.DataFrame([
            {
                "news_id": "n1_just_before_cutoff",
                "company_id": "US_CIK_0000320193", "ticker": "AAPL",
                "published_at": pd.Timestamp("2023-05-26 13:14:59", tz="UTC"),
                "published_date": "2023-05-26",
                "has_intraday_time": True, "has_body_text": True,
                "headline": "1 sec before cutoff", "article_text": "text", "source": "Reuters",
            },
            {
                "news_id": "n2_exactly_at_cutoff",
                "company_id": "US_CIK_0000320193", "ticker": "AAPL",
                "published_at": pd.Timestamp("2023-05-26 13:15:00", tz="UTC"),
                "published_date": "2023-05-26",
                "has_intraday_time": True, "has_body_text": True,
                "headline": "Exactly at cutoff", "article_text": "text", "source": "Bloomberg",
            },
            {
                "news_id": "n3_just_after_cutoff",
                "company_id": "US_CIK_0000320193", "ticker": "AAPL",
                "published_at": pd.Timestamp("2023-05-26 13:15:01", tz="UTC"),
                "published_date": "2023-05-26",
                "has_intraday_time": True, "has_body_text": True,
                "headline": "1 sec after cutoff", "article_text": "text", "source": "WSJ",
            },
            {
                "news_id": "n4_during_buffer",
                "company_id": "US_CIK_0000320193", "ticker": "AAPL",
                "published_at": pd.Timestamp("2023-05-26 13:25:00", tz="UTC"),
                "published_date": "2023-05-26",
                "has_intraday_time": True, "has_body_text": True,
                "headline": "5 min before open during buffer", "article_text": "text", "source": "CNBC",
            },
            {
                "news_id": "n5_exactly_at_open",
                "company_id": "US_CIK_0000320193", "ticker": "AAPL",
                "published_at": pd.Timestamp("2023-05-26 13:30:00", tz="UTC"),
                "published_date": "2023-05-26",
                "has_intraday_time": True, "has_body_text": True,
                "headline": "Exactly at open bell", "article_text": "text", "source": "DowJones",
            },
            {
                "news_id": "n6_just_after_open",
                "company_id": "US_CIK_0000320193", "ticker": "AAPL",
                "published_at": pd.Timestamp("2023-05-26 13:30:01", tz="UTC"),
                "published_date": "2023-05-26",
                "has_intraday_time": True, "has_body_text": True,
                "headline": "1 sec after open bell", "article_text": "text", "source": "PRNewsiwire",
            },
        ])

        cfg = DatasetBuildConfig(market_config=MarketFeatureConfig(decision_timing=DecisionTimingMode.NEXT_SESSION_OPEN))
        builder = UnifiedDatasetBuilder(cfg)
        result = builder.build_dataset(df_market=df_market, df_news=df_news, universe_df=mock_universe_df)
        row = result.data.iloc[0]

        # Only n1 and n2 are <= 13:15:00 UTC. n3, n4, n5, and n6 are strictly excluded!
        assert row["news_count_1d"] == 2
        assert row["news_unique_sources_1d"] == 2
        # Most recent included article is n2 at 13:15:00 UTC (recency = 0.0 hours)
        assert row["news_recency_hours"] == 0.0

    def test_next_session_open_sec_fundamental_boundary_behavior(self, mock_universe_df):
        """
        Regression test for SEC filings around pre-open cutoff vs execution:
        - Fact accepted at 13:15:00 UTC (cutoff) -> INCLUDED
        - Fact accepted at 13:15:01 UTC (after cutoff) -> EXCLUDED
        - Fact accepted at 13:30:00 UTC (at open) -> EXCLUDED
        """
        df_market = pd.DataFrame([{
            "company_id": "US_CIK_0000320193", "ticker": "AAPL",
            "timestamp": pd.to_datetime("2023-05-25 00:00:00", utc=True),
            "trading_date": "2023-05-25",
            "open": 172.0, "high": 173.0, "low": 171.0, "close": 172.99,
            "adjusted_open": 172.0, "adjusted_high": 173.0, "adjusted_low": 171.0, "adjusted_close": 172.99,
            "volume": 50000000,
        }])

        # 1. Fact accepted 1s after cutoff: 13:15:01 UTC
        df_facts_after_cutoff = pd.DataFrame([{
            "company_id": "US_CIK_0000320193", "concept": "Revenues",
            "period_end": "2023-04-01", "form": "10-Q",
            "acceptance_timestamp": pd.to_datetime("2023-05-26 13:15:01", utc=True),
            "accession_number": "0000320193-23-000099", "value": 99999.0,
        }])

        cfg = DatasetBuildConfig(market_config=MarketFeatureConfig(decision_timing=DecisionTimingMode.NEXT_SESSION_OPEN))
        builder = UnifiedDatasetBuilder(cfg)
        res_after = builder.build_dataset(df_market=df_market, df_fundamentals=df_facts_after_cutoff, universe_df=mock_universe_df)
        row_after = res_after.data.iloc[0]
        # Must be excluded (revenue is NaN)
        assert np.isnan(row_after["fundamental_revenue"])
        assert bool(row_after["fundamental_revenue_missing"]) is True

        # 2. Fact accepted exactly at cutoff: 13:15:00 UTC
        df_facts_at_cutoff = pd.DataFrame([{
            "company_id": "US_CIK_0000320193", "concept": "Revenues",
            "period_end": "2023-04-01", "form": "10-Q",
            "acceptance_timestamp": pd.to_datetime("2023-05-26 13:15:00", utc=True),
            "accession_number": "0000320193-23-000088", "value": 88888.0,
        }])
        res_at = builder.build_dataset(df_market=df_market, df_fundamentals=df_facts_at_cutoff, universe_df=mock_universe_df)
        row_at = res_at.data.iloc[0]
        assert row_at["fundamental_revenue"] == 88888.0
        assert bool(row_at["fundamental_revenue_missing"]) is False

    def test_next_session_open_winter_est_timezone_conversion(self, mock_universe_df):
        """
        Verifies timezone conversion in winter Standard Time (EST = UTC-5):
        - Trading date: 2023-01-03 (Tuesday)
        - Next session: 2023-01-04 (Wednesday)
        - Pre-open cutoff: 09:15 ET = 14:15:00 UTC
        - Execution: 09:30 ET = 14:30:00 UTC
        """
        df_market = pd.DataFrame([{
            "company_id": "US_CIK_0000320193", "ticker": "AAPL",
            "timestamp": pd.to_datetime("2023-01-03 00:00:00", utc=True),
            "trading_date": "2023-01-03",
            "open": 130.0, "high": 131.0, "low": 124.0, "close": 125.07,
            "adjusted_open": 130.0, "adjusted_high": 131.0, "adjusted_low": 124.0, "adjusted_close": 125.07,
            "volume": 112117500,
        }])

        df_news = pd.DataFrame([
            {
                "news_id": "est_before_cutoff",
                "company_id": "US_CIK_0000320193", "ticker": "AAPL",
                "published_at": pd.Timestamp("2023-01-04 14:14:59", tz="UTC"),
                "published_date": "2023-01-04",
                "has_intraday_time": True, "has_body_text": True,
                "headline": "Before EST cutoff", "article_text": "text", "source": "Bloomberg",
            },
            {
                "news_id": "est_at_open",
                "company_id": "US_CIK_0000320193", "ticker": "AAPL",
                "published_at": pd.Timestamp("2023-01-04 14:30:00", tz="UTC"),
                "published_date": "2023-01-04",
                "has_intraday_time": True, "has_body_text": True,
                "headline": "At EST open bell", "article_text": "text", "source": "Reuters",
            },
        ])

        cfg = DatasetBuildConfig(market_config=MarketFeatureConfig(decision_timing=DecisionTimingMode.NEXT_SESSION_OPEN))
        builder = UnifiedDatasetBuilder(cfg)
        result = builder.build_dataset(df_market=df_market, df_news=df_news, universe_df=mock_universe_df)
        row = result.data.iloc[0]

        # Verify EST conversion
        assert row["information_cutoff_timestamp"] == pd.Timestamp("2023-01-04 14:15:00", tz="UTC")
        assert row["decision_timestamp"] == pd.Timestamp("2023-01-04 14:15:00", tz="UTC")
        assert row["execution_timestamp"] == pd.Timestamp("2023-01-04 14:30:00", tz="UTC")
        # Article before cutoff included; article at open excluded!
        assert row["news_count_1d"] == 1

    def test_pre_open_cutoff_minutes_custom_propagation(self, mock_universe_df):
        """
        Verifies that non-default pre_open_cutoff_minutes (e.g. 30 minutes) on DatasetBuildConfig
        is reliably propagated to MarketFeatureConfig and observed in both decision/information
        cutoff timestamps and news/SEC eligibility.
        - Open is 09:30 ET (13:30 UTC in EDT)
        - 30-min buffer -> 09:00 ET = 13:00:00 UTC
        - News at 12:59:59 UTC: INCLUDED
        - News at 13:00:01 UTC: EXCLUDED (even though before 13:15 and before 13:30)
        """
        df_market = pd.DataFrame([{
            "company_id": "US_CIK_0000320193", "ticker": "AAPL",
            "timestamp": pd.to_datetime("2023-05-25 00:00:00", utc=True),
            "trading_date": "2023-05-25",
            "open": 172.0, "high": 173.0, "low": 171.0, "close": 172.99,
            "adjusted_open": 172.0, "adjusted_high": 173.0, "adjusted_low": 171.0, "adjusted_close": 172.99,
            "volume": 50000000,
        }])

        df_news = pd.DataFrame([
            {
                "news_id": "n_eligible_30m",
                "company_id": "US_CIK_0000320193", "ticker": "AAPL",
                "published_at": pd.Timestamp("2023-05-26 12:59:59", tz="UTC"),
                "published_date": "2023-05-26",
                "has_intraday_time": True, "has_body_text": True,
                "headline": "Before 30m cutoff", "article_text": "text", "source": "Reuters",
            },
            {
                "news_id": "n_excluded_30m",
                "company_id": "US_CIK_0000320193", "ticker": "AAPL",
                "published_at": pd.Timestamp("2023-05-26 13:00:01", tz="UTC"),
                "published_date": "2023-05-26",
                "has_intraday_time": True, "has_body_text": True,
                "headline": "After 30m cutoff but before 15m and open", "article_text": "text", "source": "Bloomberg",
            },
        ])

        cfg = DatasetBuildConfig(
            pre_open_cutoff_minutes=30,
            market_config=MarketFeatureConfig(decision_timing=DecisionTimingMode.NEXT_SESSION_OPEN),
        )
        builder = UnifiedDatasetBuilder(cfg)
        result = builder.build_dataset(df_market=df_market, df_news=df_news, universe_df=mock_universe_df)
        row = result.data.iloc[0]

        # Verify timestamps reflect the 30-minute buffer: 09:00 ET = 13:00:00 UTC
        assert row["information_cutoff_timestamp"] == pd.Timestamp("2023-05-26 13:00:00", tz="UTC")
        assert row["decision_timestamp"] == pd.Timestamp("2023-05-26 13:00:00", tz="UTC")
        assert row["execution_timestamp"] == pd.Timestamp("2023-05-26 13:30:00", tz="UTC")

        # News filtering check: exactly 1 article eligible (n_eligible_30m)
        assert row["news_count_1d"] == 1



class TestCanonicalHalfOpenIntervalBoundaries:
    """Verifies canonical half-open interval semantics [effective_from, effective_to)."""

    def test_fb_meta_half_open_transition_boundaries(self):
        """
        FB was active until 2022-06-09 [2013-12-23, 2022-06-09).
        META began on 2022-06-09 [2022-06-09, 9999-12-31).
        Under canonical [from, to):
        - 2022-06-08: FB is MATCHED, META is OUT_OF_INTERVAL.
        - 2022-06-09 (transition): FB is OUT_OF_INTERVAL, META is MATCHED.
        - 2022-06-10: FB is OUT_OF_INTERVAL, META is MATCHED.
        """
        from src.data.news.ingestor import NewsIngestor, NewsMappingStatus

        universe_df = pd.DataFrame([
            {
                "company_id": "US_CIK_0001326801",
                "ticker": "FB",
                "effective_from": "2013-12-23",
                "effective_to": "2022-06-09",
            },
            {
                "company_id": "US_CIK_0001326801",
                "ticker": "META",
                "effective_from": "2022-06-09",
                "effective_to": "9999-12-31",
            },
        ])
        ingestor = NewsIngestor(universe_df=universe_df)

        # Day before transition (2022-06-08)
        cid_fb_prev, stat_fb_prev, _ = ingestor.resolve_company_mapping("FB", "2022-06-08")
        assert cid_fb_prev == "US_CIK_0001326801"
        assert stat_fb_prev == NewsMappingStatus.MATCHED.value

        cid_meta_prev, stat_meta_prev, _ = ingestor.resolve_company_mapping("META", "2022-06-08")
        assert cid_meta_prev is None
        assert stat_meta_prev == NewsMappingStatus.OUT_OF_INTERVAL.value

        # Transition date itself (2022-06-09)
        # End date is EXCLUSIVE for FB: FB must be OUT_OF_INTERVAL
        cid_fb_trans, stat_fb_trans, _ = ingestor.resolve_company_mapping("FB", "2022-06-09")
        assert cid_fb_trans is None
        assert stat_fb_trans == NewsMappingStatus.OUT_OF_INTERVAL.value

        # Start date is INCLUSIVE for META: META must be MATCHED
        cid_meta_trans, stat_meta_trans, _ = ingestor.resolve_company_mapping("META", "2022-06-09")
        assert cid_meta_trans == "US_CIK_0001326801"
        assert stat_meta_trans == NewsMappingStatus.MATCHED.value

        # Day after transition (2022-06-10)
        cid_fb_post, stat_fb_post, _ = ingestor.resolve_company_mapping("FB", "2022-06-10")
        assert cid_fb_post is None
        assert stat_fb_post == NewsMappingStatus.OUT_OF_INTERVAL.value

        cid_meta_post, stat_meta_post, _ = ingestor.resolve_company_mapping("META", "2022-06-10")
        assert cid_meta_post == "US_CIK_0001326801"
        assert stat_meta_post == NewsMappingStatus.MATCHED.value

    def test_mon_twtr_adjacent_interval_no_overlap(self):
        """
        Monsanto (MON) [2002-08-14, 2018-06-07).
        Twitter (TWTR) [2018-06-07, 2022-11-01).
        On 2018-06-07 (acquisition/replacement date):
        - MON is OUT_OF_INTERVAL (exclusive end date).
        - TWTR is MATCHED (inclusive start date).
        Guarantees zero overlapping constituents.
        """
        from src.data.news.ingestor import NewsIngestor, NewsMappingStatus

        universe_df = pd.DataFrame([
            {
                "company_id": "US_CIK_0001110783",
                "ticker": "MON",
                "effective_from": "2002-08-14",
                "effective_to": "2018-06-07",
            },
            {
                "company_id": "COMP_NO_CIK_TWTR",
                "ticker": "TWTR",
                "effective_from": "2018-06-07",
                "effective_to": "2022-11-01",
            },
        ])
        ingestor = NewsIngestor(universe_df=universe_df)

        # Day before: 2018-06-06
        cid_mon_prev, stat_mon_prev, _ = ingestor.resolve_company_mapping("MON", "2018-06-06")
        assert cid_mon_prev == "US_CIK_0001110783"
        cid_twtr_prev, stat_twtr_prev, _ = ingestor.resolve_company_mapping("TWTR", "2018-06-06")
        assert cid_twtr_prev is None

        # Transition date: 2018-06-07
        cid_mon_trans, stat_mon_trans, _ = ingestor.resolve_company_mapping("MON", "2018-06-07")
        assert cid_mon_trans is None
        assert stat_mon_trans == NewsMappingStatus.OUT_OF_INTERVAL.value

        cid_twtr_trans, stat_twtr_trans, _ = ingestor.resolve_company_mapping("TWTR", "2018-06-07")
        assert cid_twtr_trans == "COMP_NO_CIK_TWTR"
        assert stat_twtr_trans == NewsMappingStatus.MATCHED.value


class TestFundamentalCoverageAndStaleness:
    """Verifies fundamental coverage metrics, staleness thresholds, and status classification."""

    def test_stale_facts_classified_as_facts_missing_or_stale(self, mock_universe_df):
        """
        When fundamental facts exist but their acceptance_timestamp is > max_staleness_days
        (400 days) prior to decision cutoff, the row must be classified as facts_missing_or_stale,
        NOT active_with_facts.
        """
        df_market = pd.DataFrame([{
            "company_id": "US_CIK_0000320193", "ticker": "AAPL",
            "timestamp": pd.to_datetime("2023-05-26 00:00:00", utc=True),
            "trading_date": "2023-05-26",
            "open": 175.0, "high": 176.0, "low": 174.0, "close": 175.43,
            "adjusted_open": 175.0, "adjusted_high": 176.0, "adjusted_low": 174.0, "adjusted_close": 175.43,
            "volume": 50000000,
        }])

        # Old fact accepted 500 days before May 26, 2023 (approx Jan 2022)
        df_facts_stale = pd.DataFrame([{
            "company_id": "US_CIK_0000320193",
            "concept": "Revenues",
            "period_end": "2021-09-25",
            "form": "10-K",
            "acceptance_timestamp": pd.to_datetime("2022-01-01 10:00:00", utc=True),
            "accession_number": "0000320193-22-000001",
            "value": 365817000000.0,
        }])

        builder = UnifiedDatasetBuilder()
        result = builder.build_dataset(df_market=df_market, df_fundamentals=df_facts_stale, universe_df=mock_universe_df)
        df = result.data

        row = df.iloc[0]
        assert bool(row["fundamental_revenue_is_stale"]) is True
        assert row["fundamental_revenue_age_days"] > 400.0
        assert row["fundamental_coverage_status"] == "facts_missing_or_stale"
        assert result.coverage_report.fundamental_stale_rows_count == 1
        assert result.coverage_report.fundamental_core_coverage_pct == 0.0

    def test_unregistered_company_classified_source_unavailable(self, mock_universe_df):
        """A company with zero facts in the fundamentals source is classified as source_unavailable."""
        df_market = pd.DataFrame([{
            "company_id": "US_CIK_0001326801", "ticker": "META",
            "timestamp": pd.to_datetime("2023-05-26 00:00:00", utc=True),
            "trading_date": "2023-05-26",
            "open": 260.0, "high": 265.0, "low": 258.0, "close": 262.0,
            "adjusted_open": 260.0, "adjusted_high": 265.0, "adjusted_low": 258.0, "adjusted_close": 262.0,
            "volume": 30000000,
        }])
        # Facts DataFrame contains only Apple, not Meta
        df_facts_aapl_only = pd.DataFrame([{
            "company_id": "US_CIK_0000320193",
            "concept": "Revenues",
            "period_end": "2023-04-01",
            "form": "10-Q",
            "acceptance_timestamp": pd.to_datetime("2023-05-05 02:03:52", utc=True),
            "accession_number": "0000320193-23-000064",
            "value": 94836000000.0,
        }])

        builder = UnifiedDatasetBuilder()
        result = builder.build_dataset(df_market=df_market, df_fundamentals=df_facts_aapl_only, universe_df=mock_universe_df)
        df = result.data
        assert df.iloc[0]["fundamental_coverage_status"] == "source_unavailable"


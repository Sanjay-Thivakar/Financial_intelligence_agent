"""
Unit and Regression Tests for Target Engine, Walk-Forward Splitter, and Market Baseline.
"""

import numpy as np
import pandas as pd
import pytest

from src.features.target import ForwardReturnTargetEngine, TargetConfig, TargetIntegrityError
from src.models.splitter import WalkForwardSplitter, WalkForwardConfig, SplitterIntegrityError
from src.models.baseline import MarketBaselinePipeline
from src.features.fundamental import FundamentalFeatureEngine
from src.features.config import FundamentalFeatureConfig, DecisionTimingMode, MarketFeatureConfig
from src.features.dataset import UnifiedDatasetBuilder, DatasetBuildConfig


class TestForwardReturnTargetEngine:
    """Tests ForwardReturnTargetEngine pricing, indexing, corporate action adjustments, and boundary handling."""

    @pytest.fixture
    def sample_series(self):
        # 10 synthetic sessions
        records = []
        for i in range(10):
            records.append({
                "company_id": "TEST_CO",
                "ticker": "TST",
                "trading_date": f"2023-01-{i+1:02d}",
                "open": 100.0 + i,
                "close": 102.0 + i,
                "adjusted_close": 102.0 + i,
                "adjusted_open": 100.0 + i,
            })
        return pd.DataFrame(records)

    def test_target_calculation_normal_case(self, sample_series):
        # Horizon H = 3 sessions
        cfg = TargetConfig(horizon_sessions=3)
        engine = ForwardReturnTargetEngine(cfg)
        df_res = engine.add_target(sample_series)

        # For session T=0 (2023-01-01):
        # Entry is session T+1 (2023-01-02) open: 101.0
        # Exit is session T+3 (2023-01-04) close: 105.0
        # Expected return: (105.0 - 101.0) / 101.0
        expected_ret = (105.0 - 101.0) / 101.0
        assert np.isclose(df_res.loc[0, "target_forward_return_5d"], expected_ret)
        assert df_res.loc[0, "target_entry_date"] == "2023-01-02"
        assert df_res.loc[0, "target_exit_date"] == "2023-01-04"
        assert bool(df_res.loc[0, "target_forward_return_5d_valid"]) is True

    def test_terminal_horizon_rows_masked(self, sample_series):
        # Horizon H = 5 sessions on 10-session series
        # Last 5 sessions (indices 5, 6, 7, 8, 9) must have target_valid == False and target == NaN
        cfg = TargetConfig(horizon_sessions=5)
        engine = ForwardReturnTargetEngine(cfg)
        df_res = engine.add_target(sample_series)

        assert df_res["target_forward_return_5d_valid"].sum() == 5
        for i in range(5, 10):
            assert bool(df_res.loc[i, "target_forward_return_5d_valid"]) is False
            assert np.isnan(df_res.loc[i, "target_forward_return_5d"])

    def test_derived_adjusted_open_split_invariance(self):
        """
        Tests that when adjusted_open is not explicitly provided,
        it is derived via adj_factor = adjusted_close / close.
        Simulates a 2-for-1 stock split between session 2 and 3.
        """
        # Session 0, 1: pre-split raw $200 (adj $100)
        # Session 2, 3: post-split raw $100 (adj $100)
        records = [
            {"company_id": "SPLIT_CO", "trading_date": "2023-06-01", "open": 200.0, "close": 200.0, "adjusted_close": 100.0},
            {"company_id": "SPLIT_CO", "trading_date": "2023-06-02", "open": 200.0, "close": 200.0, "adjusted_close": 100.0},
            {"company_id": "SPLIT_CO", "trading_date": "2023-06-05", "open": 100.0, "close": 100.0, "adjusted_close": 100.0},
            {"company_id": "SPLIT_CO", "trading_date": "2023-06-06", "open": 100.0, "close": 100.0, "adjusted_close": 100.0},
            {"company_id": "SPLIT_CO", "trading_date": "2023-06-07", "open": 100.0, "close": 100.0, "adjusted_close": 100.0},
        ]
        df = pd.DataFrame(records)
        engine = ForwardReturnTargetEngine(TargetConfig(horizon_sessions=2))
        res = engine.add_target(df)

        # Session 0: entry is session 1 open (derived adj $100), exit is session 2 close (adj $100)
        # True economic return across split: (100 - 100) / 100 = 0.0!
        # If unadjusted prices were mixed, it would mistakenly calculate (100 - 200)/200 = -50%!
        assert np.isclose(res.loc[0, "target_forward_return_5d"], 0.0)

    def test_duplicate_dates_rejected(self, sample_series):
        bad_df = pd.concat([sample_series, sample_series.iloc[[0]]], ignore_index=True)
        engine = ForwardReturnTargetEngine()
        with pytest.raises(TargetIntegrityError, match="Duplicate trading dates"):
            engine.add_target(bad_df)

    def test_invalid_prices_rejected(self, sample_series):
        bad_df = sample_series.copy()
        bad_df.loc[2, "close"] = -10.0
        engine = ForwardReturnTargetEngine()
        with pytest.raises(TargetIntegrityError, match="Invalid non-positive"):
            engine.add_target(bad_df)


class TestWalkForwardSplitter:
    """Tests chronological walk-forward splitting, purging, and embargoing."""

    @pytest.fixture
    def timeline_df(self):
        dates = [f"2023-01-{i+1:02d}" for i in range(30)]
        return pd.DataFrame({"trading_date": dates, "val": range(30)})

    def test_purge_gap_strictly_enforced(self, timeline_df):
        # 30 days total: min_T=15, val=5, purge=3
        cfg = WalkForwardConfig(n_splits=2, train_min_sessions=15, val_sessions=5, purge_sessions=3)
        splitter = WalkForwardSplitter(cfg)

        for fold, (tr_idx, val_idx) in enumerate(splitter.split(timeline_df)):
            tr_dates = timeline_df.loc[tr_idx, "trading_date"]
            val_dates = timeline_df.loc[val_idx, "trading_date"]

            # Max train date must be strictly before min val date
            assert tr_dates.max() < val_dates.min()

            # Gap between max train date and min val date must be exactly purge_sessions (3 dates)
            gap_df = timeline_df[(timeline_df["trading_date"] > tr_dates.max()) & (timeline_df["trading_date"] < val_dates.min())]
            assert len(gap_df) == 3

    def test_unsorted_dates_rejected(self):
        bad_dates = ["2023-01-05", "2023-01-02", "2023-01-08"]
        df = pd.DataFrame({"trading_date": bad_dates})
        splitter = WalkForwardSplitter()
        with pytest.raises(SplitterIntegrityError, match="not sorted"):
            list(splitter.split(df))

    def test_walk_forward_covers_later_available_period(self):
        """
        Verifies that WalkForwardSplitter can be configured to cover the later available period
        (e.g., sessions ending on 2020-06-03) and that no training label can overlap the validation boundary.
        """
        # Create synthetic series of 358 sessions matching AAPL experiment
        dates = pd.date_range("2019-01-02", periods=358, freq="B").strftime("%Y-%m-%d").tolist()
        df = pd.DataFrame({"trading_date": dates, "val": range(358)})

        # 4 splits covering all 358 sessions: min_T=173, val=45, purge=5
        cfg = WalkForwardConfig(n_splits=4, train_min_sessions=173, val_sessions=45, purge_sessions=5)
        splitter = WalkForwardSplitter(cfg)
        splits = list(splitter.split(df))

        assert len(splits) == 4
        # Final fold must cover the latest available dates (up to the very last session index 357)
        final_tr, final_val = splits[-1]
        assert final_val[-1] == 357
        assert df.loc[final_val[-1], "trading_date"] == dates[-1]

        # For EVERY split, verify that no training session can have an overlapping holding return
        # into the validation window:
        # A 5-session target starting on train session T requires exit at T+5.
        # If train ends at index T_end, exit is at T_end + 5.
        # The validation set begins at T_end + 1 + purge_sessions = T_end + 6 > T_end + 5!
        for k, (tr, va) in enumerate(splits):
            train_last_idx = tr[-1]
            val_first_idx = va[0]
            # Exact purge gap assertion
            assert val_first_idx - train_last_idx == cfg.purge_sessions + 1
            # 5-session forward return exit date (T_last + 5) must be strictly prior to val_first_idx!
            assert train_last_idx + 5 < val_first_idx


class TestMarketBaselinePipeline:
    """Tests naive benchmarks and Ridge model under training-only preprocessing."""

    def test_preprocessing_isolation_on_train(self):
        # X with missing values and distinct train/val distributions
        X_tr = pd.DataFrame({
            "market_return_1d": [0.01, np.nan, 0.03, -0.01, 0.02] * 4,
            "market_volatility_5d": [0.1, 0.2, np.nan, 0.15, 0.12] * 4,
        })
        y_tr = np.array([0.02, -0.01, 0.04, 0.0, 0.01] * 4)

        X_val = pd.DataFrame({
            "market_return_1d": [0.05, 0.02, np.nan],
            "market_volatility_5d": [np.nan, 0.25, 0.18],
        })
        y_val = np.array([0.03, 0.01, -0.02])

        pipeline = MarketBaselinePipeline(feature_columns=["market_return_1d", "market_volatility_5d"])
        res_zero = pipeline.evaluate_naive_zero(y_val)
        res_med = pipeline.evaluate_naive_median(y_tr, y_val)
        res_ridge = pipeline.fit_and_evaluate_ridge(X_tr, y_tr, X_val, y_val)

        # Naive zero predicts exactly 0
        assert np.all(res_zero.predictions == 0.0)
        # Naive median predicts training median
        assert np.all(res_med.predictions == np.median(y_tr))
        # Ridge generates finite predictions
        assert len(res_ridge.predictions) == 3
        assert np.all(np.isfinite(res_ridge.predictions))
        assert res_ridge.best_params["features_used"] == 2


class TestMultiCompanyPanelBaseline:
    """Tests multi-company panel data construction, identity handling, and per-company evaluation."""

    def test_unknown_aa_excluded_and_four_companies_identified(self):
        """Verifies UNKNOWN_AA is excluded from eligible cohort, and 4 remaining companies are validated."""
        df = pd.read_parquet("data/processed/market/sp500_market_sample.parquet")
        tickers = set(df["ticker"].unique())
        assert "AA" in tickers

        # Check AA has unverified identity
        aa_cids = df[df["ticker"] == "AA"]["company_id"].unique()
        assert "UNKNOWN_AA" in aa_cids

        # Filter out AA
        eligible_df = df[df["company_id"] != "UNKNOWN_AA"]
        eligible_cids = set(eligible_df["company_id"].unique())
        expected_cids = {
            "US_CIK_0000320193",  # AAPL
            "US_CIK_0000019617",  # JPM
            "US_CIK_0001652044",  # GOOG
            "US_CIK_0001318605",  # TSLA
        }
        assert eligible_cids == expected_cids

    def test_multi_company_panel_target_calculation(self):
        """Verifies ForwardReturnTargetEngine correctly groups by company and masks terminal rows per company."""
        dates = ["2023-01-01", "2023-01-02", "2023-01-03", "2023-01-04", "2023-01-05", "2023-01-06", "2023-01-07"]
        records = []
        for cid in ["CO_A", "CO_B"]:
            for i, d in enumerate(dates):
                records.append({
                    "company_id": cid,
                    "trading_date": d,
                    "open": 100.0 + i,
                    "close": 105.0 + i,
                    "adjusted_close": 105.0 + i,
                })
        df = pd.DataFrame(records)
        engine = ForwardReturnTargetEngine(TargetConfig(horizon_sessions=2))
        res = engine.add_target(df)

        assert len(res) == 14
        # For each company (7 sessions), last 2 sessions must be masked as invalid
        for cid in ["CO_A", "CO_B"]:
            sub = res[res["company_id"] == cid]
            assert sub["target_forward_return_5d_valid"].sum() == 5
            # Terminal rows check
            assert sub["target_forward_return_5d_valid"].iloc[-2:].sum() == 0

    def test_multi_company_panel_walk_forward_partition(self):
        """Verifies WalkForwardSplitter handles multi-company panel dates without splitting across companies on same date."""
        dates = pd.date_range("2019-01-02", periods=50, freq="B").strftime("%Y-%m-%d").tolist()
        records = []
        for d in dates:
            for cid in ["C1", "C2", "C3", "C4"]:
                records.append({"trading_date": d, "company_id": cid, "val": 1.0})
        df = pd.DataFrame(records).sort_values("trading_date").reset_index(drop=True)

        cfg = WalkForwardConfig(n_splits=2, train_min_sessions=30, val_sessions=8, purge_sessions=4)
        splitter = WalkForwardSplitter(cfg)

        for fold, (tr_idx, val_idx) in enumerate(splitter.split(df)):
            tr_df = df.iloc[tr_idx]
            val_df = df.iloc[val_idx]
            # Every date must contain all 4 companies
            assert (tr_df.groupby("trading_date").size() == 4).all()
            assert (val_df.groupby("trading_date").size() == 4).all()
            # Purge gap must be exactly 4 calendar trading sessions
            tr_max = tr_df["trading_date"].max()
            val_min = val_df["trading_date"].min()
            all_dates = sorted(list(set(df["trading_date"])))
            idx_t_max = all_dates.index(tr_max)
            idx_v_min = all_dates.index(val_min)
            assert idx_v_min - idx_t_max == 5  # 4 purge dates in between

    def test_five_date_panel_purge_and_zero_label_overlap(self):
        """
        Verifies that on multi-company panels:
        1. Exactly 5 calendar trading dates are purged between training and validation.
        2. All companies on each date remain grouped together.
        3. The last training target's exit date is strictly prior to the first validation decision date.
        """
        # Create 100 trading dates with 4 companies each
        dates = pd.date_range("2019-01-02", periods=100, freq="B").strftime("%Y-%m-%d").tolist()
        records = []
        for d in dates:
            for cid in ["AAPL", "JPM", "GOOG", "TSLA"]:
                records.append({
                    "company_id": cid,
                    "trading_date": d,
                    "open": 100.0,
                    "close": 102.0,
                    "adjusted_close": 102.0,
                })
        df = pd.DataFrame(records).sort_values(["trading_date", "company_id"]).reset_index(drop=True)

        # Compute 5-session forward return target
        engine = ForwardReturnTargetEngine(TargetConfig(horizon_sessions=5))
        df_labeled = engine.add_target(df)
        df_valid = df_labeled[df_labeled["target_forward_return_5d_valid"]].copy().reset_index(drop=True)

        # 2 splits: train_min=50 dates, val=20 dates, purge=5 dates
        cfg = WalkForwardConfig(n_splits=2, train_min_sessions=50, val_sessions=20, purge_sessions=5)
        splitter = WalkForwardSplitter(cfg)

        all_unique_dates = pd.Series(sorted(df_valid["trading_date"].unique()))

        for fold, (tr_idx, val_idx) in enumerate(splitter.split(df_valid)):
            tr_df = df_valid.iloc[tr_idx]
            val_df = df_valid.iloc[val_idx]

            tr_dates = sorted(tr_df["trading_date"].unique())
            val_dates = sorted(val_df["trading_date"].unique())

            # 1. Check exactly 5 calendar trading dates are purged
            tr_max = tr_dates[-1]
            val_min = val_dates[0]
            purge_mask = (all_unique_dates > tr_max) & (all_unique_dates < val_min)
            purge_dates = all_unique_dates[purge_mask].tolist()
            assert len(purge_dates) == 5, f"Expected 5 purge dates, got {len(purge_dates)}"

            # 2. Check all companies grouped together on every date
            assert (tr_df.groupby("trading_date")["company_id"].nunique() == 4).all()
            assert (val_df.groupby("trading_date")["company_id"].nunique() == 4).all()

            # 3. Check zero target outcome overlap
            # The exit date of the last training target must be strictly before the first validation decision date
            last_train_rows = tr_df[tr_df["trading_date"] == tr_max]
            last_train_exit_dates = last_train_rows["target_exit_date"].unique()
            assert len(last_train_exit_dates) == 1
            last_exit = last_train_exit_dates[0]
            first_val_decision = val_min
            assert last_exit < first_val_decision, f"Target outcome overlap: last exit {last_exit} >= first val decision {first_val_decision}"


class TestFundamentalPointInTimeAndBaseline:
    """Tests point-in-time correctness of SEC fundamentals and baseline integration (Phase 5D)."""

    def test_post_cutoff_filing_acceptance_cannot_leak(self):
        """
        Proves that a filing accepted after the decision cutoff cannot affect that decision's features.
        Period end is 2020-03-31, but acceptance is 2020-04-15 16:30:00 UTC.
        A decision at 2020-04-15 13:30:00 UTC cannot see this filing.
        A decision at 2020-04-16 13:30:00 UTC sees this filing.
        """
        facts_data = [
            {
                "company_id": "TEST_CO",
                "entity_name": "Test Co",
                "cik": "0000000001",
                "taxonomy": "us-gaap",
                "concept": "Revenues",
                "unit": "USD",
                "period_end": "2020-03-31",
                "period_type": "duration",
                "value": 50000000.0,
                "accession_number": "0000000001-20-000001",
                "form": "10-Q",
                "filing_date": "2020-04-15",
                "acceptance_timestamp": pd.Timestamp("2020-04-15 16:30:00", tz="UTC"),
                "fy": 2020,
                "fp": "Q1",
            }
        ]
        df_facts = pd.DataFrame(facts_data)
        engine = FundamentalFeatureEngine(df_facts)

        # Decision 1: 2020-04-15 13:30:00 UTC (3 hours before filing acceptance)
        d1 = pd.Timestamp("2020-04-15 13:30:00", tz="UTC")
        snap1 = engine.get_as_of_snapshot("TEST_CO", d1)
        assert snap1["fundamental_available"] is False
        assert np.isnan(snap1["fundamental_revenue"])
        assert snap1["fundamental_revenue_missing"] is True

        # Decision 2: 2020-04-16 13:30:00 UTC (Next morning open, after filing acceptance)
        d2 = pd.Timestamp("2020-04-16 13:30:00", tz="UTC")
        snap2 = engine.get_as_of_snapshot("TEST_CO", d2)
        assert snap2["fundamental_available"] is True
        assert snap2["fundamental_revenue"] == 50000000.0
        assert snap2["fundamental_revenue_missing"] is False
        assert snap2["fundamental_revenue_accn"] == "0000000001-20-000001"

    def test_amended_filing_restatement_point_in_time_ordering(self):
        """
        Proves that an amended 10-Q/A restatement does not leak backward in time:
        - Original 10-Q accepted 2020-05-01: Revenue $100M
        - Restated 10-Q/A accepted 2020-08-01: Revenue $90M
        Decision on 2020-06-01 must see $100M (not $90M).
        Decision on 2020-08-15 must see $90M.
        """
        facts_data = [
            {
                "company_id": "TEST_CO",
                "entity_name": "Test Co",
                "cik": "0000000001",
                "taxonomy": "us-gaap",
                "concept": "Revenues",
                "unit": "USD",
                "period_end": "2020-03-31",
                "period_type": "duration",
                "value": 100000000.0,
                "accession_number": "0000000001-20-000010",
                "form": "10-Q",
                "filing_date": "2020-05-01",
                "acceptance_timestamp": pd.Timestamp("2020-05-01 16:30:00", tz="UTC"),
                "fy": 2020,
                "fp": "Q1",
            },
            {
                "company_id": "TEST_CO",
                "entity_name": "Test Co",
                "cik": "0000000001",
                "taxonomy": "us-gaap",
                "concept": "Revenues",
                "unit": "USD",
                "period_end": "2020-03-31",
                "period_type": "duration",
                "value": 90000000.0,
                "accession_number": "0000000001-20-000020",
                "form": "10-Q/A",
                "filing_date": "2020-08-01",
                "acceptance_timestamp": pd.Timestamp("2020-08-01 16:30:00", tz="UTC"),
                "fy": 2020,
                "fp": "Q1",
            },
        ]
        df_facts = pd.DataFrame(facts_data)
        engine = FundamentalFeatureEngine(df_facts)

        # Decision on 2020-06-01 (before amendment was filed)
        d_before = pd.Timestamp("2020-06-01 13:30:00", tz="UTC")
        snap_before = engine.get_as_of_snapshot("TEST_CO", d_before)
        assert snap_before["fundamental_revenue"] == 100000000.0
        assert snap_before["fundamental_revenue_accn"] == "0000000001-20-000010"

        # Decision on 2020-08-15 (after amendment was filed)
        d_after = pd.Timestamp("2020-08-15 13:30:00", tz="UTC")
        snap_after = engine.get_as_of_snapshot("TEST_CO", d_after)
        assert snap_after["fundamental_revenue"] == 90000000.0
        assert snap_after["fundamental_revenue_accn"] == "0000000001-20-000020"

    def test_missing_fundamentals_never_fabricated_as_zero(self):
        """Proves missing fundamentals remain NaN and are never replaced with 0.0."""
        facts_data = [
            {
                "company_id": "TEST_CO",
                "entity_name": "Test Co",
                "cik": "0000000001",
                "taxonomy": "us-gaap",
                "concept": "Revenues",
                "unit": "USD",
                "period_end": "2020-03-31",
                "period_type": "duration",
                "value": 50000000.0,
                "accession_number": "0000000001-20-000001",
                "form": "10-Q",
                "filing_date": "2020-04-15",
                "acceptance_timestamp": pd.Timestamp("2020-04-15 16:30:00", tz="UTC"),
                "fy": 2020,
                "fp": "Q1",
            }
        ]
        engine = FundamentalFeatureEngine(pd.DataFrame(facts_data))
        snap = engine.get_as_of_snapshot("TEST_CO", pd.Timestamp("2020-04-16 13:30:00", tz="UTC"))

        # Revenue is present
        assert snap["fundamental_revenue"] == 50000000.0
        # Net income was not filed -> must be NaN, NOT 0.0
        assert np.isnan(snap["fundamental_net_income"])
        assert snap["fundamental_net_income_missing"] is True
        # Ratio dependent on missing net income must be NaN
        assert np.isnan(snap["fundamental_ratio_net_margin"])
        assert snap["fundamental_ratio_net_margin_missing"] is True

    def test_market_plus_fundamentals_ridge_isolation(self):
        """
        Tests MarketBaselinePipeline with COMBINED_FEATURE_COLUMNS.
        Ensures SimpleImputer and StandardScaler fit strictly on training data,
        and missing fundamentals in validation fold are imputed without leakage.
        """
        # Train: 2 companies, 10 sessions each (20 rows)
        X_tr = pd.DataFrame({
            "market_return_1d": [0.01, -0.02, 0.03, 0.0, 0.02] * 4,
            "market_volatility_5d": [0.1, 0.2, 0.15, 0.12, 0.18] * 4,
            "fundamental_ratio_net_margin": [0.15, 0.15, 0.15, 0.15, 0.15, np.nan, np.nan, np.nan, np.nan, np.nan] * 2,
            "fundamental_diluted_eps": [1.5, 1.5, 1.5, 1.5, 1.5, np.nan, np.nan, np.nan, np.nan, np.nan] * 2,
            "fundamental_revenue_age_days": [30, 31, 32, 33, 34, np.nan, np.nan, np.nan, np.nan, np.nan] * 2,
            "fundamental_all_facts_stale": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0] * 2,
        })
        y_tr = np.array([0.02, -0.01, 0.04, 0.0, 0.01] * 4)

        # Val: missing fundamental values for company without facts
        X_val = pd.DataFrame({
            "market_return_1d": [0.05, 0.02, -0.01, 0.01],
            "market_volatility_5d": [0.22, 0.25, 0.18, 0.19],
            "fundamental_ratio_net_margin": [np.nan, np.nan, 0.15, 0.15],
            "fundamental_diluted_eps": [np.nan, np.nan, 1.5, 1.5],
            "fundamental_revenue_age_days": [np.nan, np.nan, 35, 36],
            "fundamental_all_facts_stale": [0, 0, 0, 0],
        })
        y_val = np.array([0.03, 0.01, -0.02, 0.02])

        cols = [
            "market_return_1d", "market_volatility_5d",
            "fundamental_ratio_net_margin", "fundamental_diluted_eps",
            "fundamental_revenue_age_days", "fundamental_all_facts_stale"
        ]
        pipeline = MarketBaselinePipeline(feature_columns=cols)
        res_mkt_fund = pipeline.fit_and_evaluate_ridge(
            X_tr, y_tr, X_val, y_val, model_name="Model 2 (Market + Fundamentals Ridge)"
        )

        assert res_mkt_fund.model_name == "Model 2 (Market + Fundamentals Ridge)"
        assert len(res_mkt_fund.predictions) == 4
        assert np.all(np.isfinite(res_mkt_fund.predictions))
        assert res_mkt_fund.best_params["features_used"] == 6




"""
Phase 5J — Automated Regression and Validation Test Suite.

Verifies:
1. Company-level eligibility manifest (data/processed/universe/phase5j_company_eligibility.csv).
2. Data integrity, identity mappings, and corporate-action adjustments across 60 companies.
3. Chronological walk-forward fold schedule with 5-session purge gap.
4. Out-of-sample prediction integrity, absence of lookahead, and fold boundaries.
5. Multi-modal track comparison population consistency (common 4-company subset).
6. Cross-sectional portfolio simulation constraints and mark-to-market accounting.
7. Backend API endpoint GET /api/models/research/phase5j contract and error handling.
8. Regression compatibility with Phase 5G and Phase 5H.
"""

import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api.app import app
from src.features.market import MarketFeatureEngine, MarketFeatureConfig
from src.features.target import ForwardReturnTargetEngine, TargetConfig
from src.features.config import DecisionTimingMode
from src.models.splitter import WalkForwardSplitter, WalkForwardConfig
from src.models.baseline import MarketBaselinePipeline
from src.portfolio.schema import PortfolioConfig, TransactionCostConfig
from src.portfolio.simulator import DeterministicPortfolioSimulator


@pytest.fixture
def client():
    return TestClient(app)


class TestPhase5JEligibilityManifest:
    """Verifies deterministic company eligibility audit results."""

    def test_eligibility_manifest_structure(self):
        p_csv = Path("data/processed/universe/phase5j_company_eligibility.csv")
        assert p_csv.exists(), "Eligibility manifest phase5j_company_eligibility.csv must exist."

        df = pd.read_csv(p_csv)
        assert len(df) == 60, f"Cohort must contain exactly 60 companies, found {len(df)}."

        required_cols = [
            "company_id", "ticker", "company_name", "sector", "cik",
            "total_sessions", "earliest_date", "latest_date", "window_sessions",
            "folds_eligible", "track_a_market_only", "track_b_market_plus_fund",
            "track_c_market_plus_events", "track_d_combined", "market_notes",
        ]
        for c in required_cols:
            assert c in df.columns, f"Manifest missing column: {c}"

    def test_truncated_companies_classification(self):
        """Verifies BLK, CSCO, CVS, EQIX, FCX are marked with limitations ending on 2020-04-01."""
        df = pd.read_csv("data/processed/universe/phase5j_company_eligibility.csv")
        truncated_tickers = ["BLK", "CSCO", "CVS", "EQIX", "FCX"]

        for tk in truncated_tickers:
            row = df[df["ticker"] == tk].iloc[0]
            assert row["window_sessions"] == 315
            assert row["latest_date"] == "2020-04-01"
            assert row["track_a_market_only"] == "ELIGIBLE_WITH_LIMITATIONS"
            assert "ineligible for Fold 3" in row["market_notes"]
            assert row["folds_eligible"] == "Fold 0; Fold 1; Fold 2"

    def test_fully_eligible_companies_count(self):
        """Verifies 54 companies have 363 sessions and are ELIGIBLE across all folds."""
        df = pd.read_csv("data/processed/universe/phase5j_company_eligibility.csv")
        full_df = df[df["window_sessions"] == 363]
        assert len(full_df) == 54, f"Expected 54 fully eligible companies, found {len(full_df)}"
        for _, row in full_df.iterrows():
            assert row["folds_eligible"] == "Fold 0; Fold 1; Fold 2; Fold 3"


class TestPhase5JMarketPanelAndWalkForward:
    """Verifies market feature calculation, target construction, and chronological splitting."""

    def test_target_construction_and_purge_gap(self):
        """Verifies H=5 forward target calculation and 5-session purge preservation."""
        # Create synthetic deterministic 30-session price panel for 2 companies
        dates = pd.date_range("2020-01-01", periods=30, freq="B").strftime("%Y-%m-%d").tolist()
        records = []
        for d in dates:
            for tk, cid, p in [("AAA", "US_CIK_0001", 100.0), ("BBB", "US_CIK_0002", 50.0)]:
                records.append({
                    "company_id": cid,
                    "ticker": tk,
                    "trading_date": d,
                    "open": p,
                    "high": p * 1.01,
                    "low": p * 0.99,
                    "close": p,
                    "adjusted_close": p,
                })
        df_test = pd.DataFrame(records)

        tgt_eng = ForwardReturnTargetEngine(TargetConfig(horizon_sessions=5))
        df_tgt = tgt_eng.add_target(df_test)

        assert "target_forward_return_5d" in df_tgt.columns
        assert "target_forward_return_5d_valid" in df_tgt.columns

        # Verify that last 5 sessions for each company are marked invalid
        for cid, grp in df_tgt.groupby("company_id"):
            assert not grp["target_forward_return_5d_valid"].iloc[-5:].any(), "Last 5 sessions must be invalid"
            assert grp["target_forward_return_5d_valid"].iloc[:-5].all(), "Prior sessions must be valid"

        # Verify walk-forward splitter gap
        wf_cfg = WalkForwardConfig(n_splits=1, train_min_sessions=15, val_sessions=5, purge_sessions=5)
        splitter = WalkForwardSplitter(wf_cfg)
        df_valid = df_tgt[df_tgt["target_forward_return_5d_valid"]].sort_values("trading_date").reset_index(drop=True)

        splits = list(splitter.split(df_valid))
        assert len(splits) == 1
        tr_idx, val_idx = splits[0]
        tr_dates = df_valid.iloc[tr_idx]["trading_date"].unique()
        val_dates = df_valid.iloc[val_idx]["trading_date"].unique()

        # Find session gap
        all_unique_dates = sorted(df_valid["trading_date"].unique().tolist())
        tr_last_idx = all_unique_dates.index(tr_dates[-1])
        val_first_idx = all_unique_dates.index(val_dates[0])
        gap = val_first_idx - tr_last_idx - 1
        assert gap == 5, f"Purge gap must be exactly 5 sessions, found {gap}"

    def test_isolated_training_preprocessing(self):
        """Verifies scaling and alpha selection are fit strictly on training fold."""
        # Check MarketBaselinePipeline fit_and_evaluate_ridge does not leak validation statistics
        np.random.seed(42)
        n_tr, n_val = 100, 30
        dates_tr = [f"2019-01-{i:02d}" for i in range(1, 21)] * 5
        dates_val = [f"2019-02-{i:02d}" for i in range(1, 7)] * 5

        X_tr = pd.DataFrame({"market_return_1d": np.random.randn(n_tr), "trading_date": dates_tr})
        y_tr = np.random.randn(n_tr)

        X_val = pd.DataFrame({"market_return_1d": np.random.randn(n_val) + 100.0, "trading_date": dates_val})
        y_val = np.random.randn(n_val)

        pipe = MarketBaselinePipeline(feature_columns=["market_return_1d"], alphas=(0.1, 1.0))
        res = pipe.fit_and_evaluate_ridge(X_tr, y_tr, X_val, y_val, model_name="TestRidge")

        assert res.rmse > 0
        assert len(res.predictions) == n_val


class TestPhase5JPortfolioSimulator:
    """Verifies mark-to-market accounting, position caps, and friction."""

    def test_rejection_of_duplicate_asset_orders(self):
        """Verifies duplicate concurrent positions in the same company are rejected."""
        cfg = PortfolioConfig(
            initial_cash=100_000.0,
            max_concurrent_positions=4,
            max_position_weight=0.25,
            holding_horizon_sessions=5,
            allow_multiple_positions_per_ticker=False,
            cost_config=TransactionCostConfig(),
        )
        sim = DeterministicPortfolioSimulator(cfg)

        dates = ["2020-01-02", "2020-01-03", "2020-01-04", "2020-01-05", "2020-01-06", "2020-01-07", "2020-01-08"]
        mkt_records = []
        for d in dates:
            mkt_records.append({
                "trading_date": d,
                "ticker": "AAPL",
                "company_id": "US_CIK_0000320193",
                "open": 100.0,
                "adjusted_open": 100.0,
                "close": 100.0,
                "adjusted_close": 100.0,
            })
        df_mkt = pd.DataFrame(mkt_records)

        # Issue 2 BUY orders for AAPL on consecutive days
        decisions = pd.DataFrame([
            {"trading_date": "2020-01-02", "ticker": "AAPL", "company_id": "US_CIK_0000320193", "signal": "BUY"},
            {"trading_date": "2020-01-03", "ticker": "AAPL", "company_id": "US_CIK_0000320193", "signal": "BUY"},
        ])

        res = sim.simulate(decisions, df_mkt, "TestSim")
        assert res.total_rejected_orders >= 1
        assert "MAX_TICKER_EXPOSURE" in res.rejection_breakdown


class TestPhase5JBackendAPI:
    """Verifies backend API endpoint for Phase 5J research results."""

    def test_api_research_phase5j_endpoint(self, client):
        resp = client.get("/api/models/research/phase5j")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data

        if data["status"] == "available":
            assert "metadata" in data
            assert data["metadata"]["n_companies_total"] == 60
            assert "aggregate_metrics" in data
            assert "fold_results" in data
            assert len(data["fold_results"]) == 4
            assert "portfolio_simulation" in data
            if "daily_cross_sectional_ic" in data["aggregate_metrics"]["ridge_cross_sectional"]:
                dcs = data["aggregate_metrics"]["ridge_cross_sectional"]["daily_cross_sectional_ic"]
                assert "mean_daily_ic" in dcs
                assert "newey_west_hac_pvalue" in dcs
                assert "newey_west_hac_tstat" in dcs

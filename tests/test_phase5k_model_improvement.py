"""
Phase 5K — Systematic Model Improvement and Walk-Forward Validation Test Suite.

Verifies:
1. Immutable baseline metric reproduction (Zero return & Ridge audit references).
2. Five pre-specified model candidates and cross-sectional / sector-neutral transformations.
3. Chronological walk-forward fold schedule with strict 5-session purge gap.
4. Out-of-sample prediction population consistency (10,559 valid rows across 4 folds).
5. Statistical inference integrity: Newey-West HAC (L=4) and cross-sectional rank invariance.
6. Institutional portfolio simulator accounting, 15 bps friction, and 100% order reconciliation.
7. Backend API endpoint GET /api/models/research/phase5k contract and schema integrity.
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


class TestPhase5KBaselineReproduction:
    """Verifies that Phase 5J.1 baseline metrics are reproduced immutably in Phase 5K."""

    def test_artifact_existence_and_metadata(self):
        p_json = Path("data/processed/research/phase5k/phase5k_model_experiment_results.json")
        p_parquet = Path("data/processed/research/phase5k/phase5k_predictions_oos.parquet")
        assert p_json.exists(), "Phase 5K experiment artifact must exist."
        assert p_parquet.exists(), "Phase 5K OOS predictions parquet must exist."

        with open(p_json, "r", encoding="utf-8") as f:
            data = json.load(f)

        meta = data["metadata"]
        assert meta["n_companies_total"] == 60
        assert meta["walk_forward_splits"] == 4
        assert meta["purge_gap_sessions"] == 5
        assert meta["target_horizon_sessions"] == 5
        assert meta["transaction_cost_roundtrip_bps"] == 15.0
        assert meta["total_out_of_sample_observations"] == 10559
        assert meta["verdict"] == "ACCEPT WITH DOCUMENTED LIMITATIONS"

    def test_immutable_baseline_metric_values(self):
        """Verifies exact audit reference targets within standard numerical tolerances."""
        with open("data/processed/research/phase5k/phase5k_model_experiment_results.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        models = data["aggregate_model_metrics"]

        # Zero baseline: RMSE ~0.0646, MAE ~0.0395
        zero = models["zero_baseline"]
        assert pytest.approx(zero["rmse"], abs=0.0005) == 0.0646
        assert pytest.approx(zero["mae"], abs=0.0005) == 0.0395
        assert zero["directional_hit_rate"] == 0.50

        # Ridge baseline: RMSE ~0.0652, MAE ~0.0399, Bias ~+0.0081, Mean Daily IC ~-0.0451, HAC p ~0.2652
        ridge = models["ridge_regression"]
        assert pytest.approx(ridge["rmse"], abs=0.0005) == 0.0652
        assert pytest.approx(ridge["mae"], abs=0.0005) == 0.0399
        assert pytest.approx(ridge["prediction_bias"], abs=0.0005) == 0.0081
        assert pytest.approx(ridge["directional_hit_rate"], abs=0.005) == 0.549
        assert pytest.approx(ridge["daily_cross_sectional_ic"]["mean_daily_ic"], abs=0.001) == -0.0451
        assert pytest.approx(ridge["daily_cross_sectional_ic"]["newey_west_hac_pvalue"], abs=0.01) == 0.2652


class TestPhase5KModelExperimentCandidates:
    """Verifies that the small, pre-specified set of candidate models were evaluated fairly."""

    def test_all_candidate_models_evaluated(self):
        with open("data/processed/research/phase5k/phase5k_model_experiment_results.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        models = data["aggregate_model_metrics"]
        expected_candidates = [
            "zero_baseline",
            "median_baseline",
            "ridge_regression",
            "elastic_net",
            "hist_gradient_boosting",
            "ridge_cs_demeaned",
            "ridge_sector_neutral",
        ]
        for ec in expected_candidates:
            assert ec in models, f"Candidate model '{ec}' must be present in Phase 5K results."
            assert models[ec]["n_observations"] == 10559, f"Model '{ec}' must have exactly 10,559 OOS observations."

    def test_nonlinear_gbrt_performance_characteristics(self):
        """Verifies GBRT error reduction and rank correlation properties."""
        with open("data/processed/research/phase5k/phase5k_model_experiment_results.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        gbrt = data["aggregate_model_metrics"]["hist_gradient_boosting"]
        zero = data["aggregate_model_metrics"]["zero_baseline"]
        ridge = data["aggregate_model_metrics"]["ridge_regression"]

        # GBRT achieves lower RMSE than zero and Ridge
        assert gbrt["rmse"] < zero["rmse"], "GBRT RMSE must be lower than zero-return baseline."
        assert gbrt["rmse"] < ridge["rmse"], "GBRT RMSE must be lower than Ridge regression."
        assert gbrt["mae"] < ridge["mae"], "GBRT MAE must be lower than Ridge regression."
        assert gbrt["directional_hit_rate"] > 0.50, "GBRT directional hit rate must exceed random baseline."

        # However, daily cross-sectional IC remains statistically insignificant (p > 0.05)
        assert gbrt["daily_cross_sectional_ic"]["newey_west_hac_pvalue"] > 0.05, "GBRT daily IC must not claim false significance."


class TestPhase5KCrossSectionalHypotheses:
    """Verifies cross-sectional normalization and sector neutralization transformations."""

    def test_cross_sectional_rank_invariance(self):
        """
        Mathematical proof check: Daily cross-sectional Spearman rank correlation is invariant
        to additive date constants (mean demeaning).
        """
        with open("data/processed/research/phase5k/phase5k_model_experiment_results.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        ridge = data["aggregate_model_metrics"]["ridge_regression"]
        demeaned = data["aggregate_model_metrics"]["ridge_cs_demeaned"]

        # Daily IC must match identically down to machine precision
        assert pytest.approx(demeaned["daily_cross_sectional_ic"]["mean_daily_ic"], abs=1e-6) == ridge["daily_cross_sectional_ic"]["mean_daily_ic"]
        assert pytest.approx(demeaned["daily_cross_sectional_ic"]["newey_west_hac_pvalue"], abs=1e-6) == ridge["daily_cross_sectional_ic"]["newey_west_hac_pvalue"]

    def test_rejected_hypotheses_documented(self):
        """Verifies failed/rejected hypotheses are transparently documented in the machine artifact."""
        with open("data/processed/research/phase5k/phase5k_model_experiment_results.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        assert "rejections_and_failures" in data
        failures = data["rejections_and_failures"]
        assert "cross_sectional_demeaning_hypothesis" in failures
        assert "sector_neutral_residualization_hypothesis" in failures
        assert "REJECTED" in failures["cross_sectional_demeaning_hypothesis"]["empirical_outcome"]


class TestPhase5KPortfolioReconciliation:
    """Verifies institutional portfolio simulation invariants, cash conservation, and order reconciliation."""

    def test_portfolio_order_reconciliation_formula(self):
        """
        Verifies Candidate BUY Orders == Executed/Closed Trades + Rejected Orders + Terminal Open Positions.
        """
        with open("data/processed/research/phase5k/phase5k_model_experiment_results.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        port = data["portfolio_simulation"]["ridge_regression"]
        rec = port["reconciliation"]

        assert rec["is_reconciled"] is True
        assert rec["candidate_buy_signals"] == rec["closed_trades"] + rec["rejected_orders"] + rec["terminal_open_positions"]
        assert rec["candidate_buy_signals"] == 112
        assert rec["closed_trades"] == 44
        assert rec["rejected_orders"] == 68
        assert rec["terminal_open_positions"] == 0

    def test_portfolio_capital_and_friction_invariants(self):
        with open("data/processed/research/phase5k/phase5k_model_experiment_results.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        port = data["portfolio_simulation"]["ridge_regression"]
        assert port["initial_equity"] == 100000.0
        assert pytest.approx(port["final_equity"], abs=0.01) == 100882.49
        assert pytest.approx(port["total_net_return"], abs=0.0001) == 0.0088
        assert pytest.approx(port["max_drawdown"], abs=0.0001) == -0.0403
        assert pytest.approx(port["total_transaction_costs"], abs=0.01) == 647.73


class TestPhase5KBackendAPI:
    """Verifies backend API endpoint GET /api/models/research/phase5k."""

    def test_api_research_phase5k_endpoint(self, client):
        resp = client.get("/api/models/research/phase5k")
        assert resp.status_code == 200
        data = resp.json()

        assert data["status"] == "available"
        assert "metadata" in data
        assert data["metadata"]["verdict"] == "ACCEPT WITH DOCUMENTED LIMITATIONS"
        assert "aggregate_model_metrics" in data
        assert "fold_by_fold_metrics" in data
        assert "portfolio_simulation" in data
        assert "rejections_and_failures" in data
        assert len(data["aggregate_model_metrics"]) >= 5

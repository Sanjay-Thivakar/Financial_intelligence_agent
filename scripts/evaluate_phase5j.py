"""
Phase 5J — Validated Cross-Sectional Training, Evaluation & Portfolio Simulation.

Evaluates:
1. Deterministic 60-company cross-sectional walk-forward training & evaluation (Track A).
2. Leakage-safe chronological splits with 5-session purge gap (Folds 0-3: 10,574 out-of-sample observations).
3. Benchmark comparison: Reference 0 (Zero Return) vs Reference 1 (Historical Median) vs Cross-Sectional Ridge.
4. Multi-modal 4-track comparison on common 4-company pilot subset (Tracks A, B, C, D).
5. Cross-sectional Decision & Risk Layer gating (uncertainty, cost friction, volatility).
6. Deterministic institutional portfolio simulation across the 60-company universe.
7. Machine-readable versioned research artifacts in data/processed/research/phase5j/.
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Tuple
from datetime import datetime, timezone

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
from scipy.stats import spearmanr, t

from src.features.market import MarketFeatureEngine, MarketFeatureConfig
from src.features.target import ForwardReturnTargetEngine, TargetConfig
from src.features.config import DecisionTimingMode
from src.features.dataset import UnifiedDatasetBuilder, DatasetBuildConfig
from src.models.splitter import WalkForwardSplitter, WalkForwardConfig
from src.models.baseline import MarketBaselinePipeline
from src.decision.schema import (
    SignalType,
    TransactionCostConfig,
    RiskGateConfig,
    DecisionContractRequest,
)
from src.decision.uncertainty import ResidualUncertaintyEstimator
from src.decision.policy import ThresholdDecisionPolicy
from src.portfolio.schema import (
    PortfolioConfig,
    RollingThresholdConfig,
    RollingThresholdResult,
)
from src.portfolio.simulator import DeterministicPortfolioSimulator
from src.portfolio.rolling import RollingThresholdSelector


def compute_directional_accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Computes directional accuracy (fraction where sign matches)."""
    valid_mask = (y_true != 0) & (y_pred != 0)
    if valid_mask.sum() == 0:
        return 0.5
    return float(np.mean(np.sign(y_true[valid_mask]) == np.sign(y_pred[valid_mask])))


def compute_ic(y_true: np.ndarray, y_pred: np.ndarray) -> Tuple[float, float]:
    """Computes Spearman Rank Information Coefficient and p-value."""
    if len(y_true) < 5 or np.all(y_pred == y_pred[0]):
        return 0.0, 1.0
    corr, pval = spearmanr(y_true, y_pred)
    return (float(corr) if not np.isnan(corr) else 0.0), (float(pval) if not np.isnan(pval) else 1.0)


def compute_daily_cross_sectional_ic(df_predictions: pd.DataFrame, min_stocks: int = 10) -> Dict[str, Any]:
    """
    Computes daily cross-sectional Spearman rank IC and dependence-aware inference
    using Newey-West HAC (L=4 for H=5 forward returns) to account for overlapping targets.
    """
    daily_records = []
    dates = sorted(df_predictions["trading_date"].unique().tolist())
    for d in dates:
        d_sub = df_predictions[df_predictions["trading_date"] == d]
        if len(d_sub) >= min_stocks:
            c, _ = spearmanr(d_sub["target_return"], d_sub["predicted_return"])
            if not np.isnan(c):
                daily_records.append((d, float(c), len(d_sub)))

    df_daily = pd.DataFrame(daily_records, columns=["trading_date", "ic", "n_stocks"])
    mean_ic = float(df_daily["ic"].mean())
    std_ic = float(df_daily["ic"].std(ddof=1))
    T_dates = len(df_daily)
    ir_ic = float(mean_ic / std_ic) if std_ic > 0 else 0.0

    # Newey-West HAC with L=4
    ic_vals = df_daily["ic"].values
    gamma_0 = float(np.var(ic_vals, ddof=1))
    L = 4
    gammas = [float(np.cov(ic_vals[:-l], ic_vals[l:])[0, 1]) for l in range(1, L + 1)]
    v_hac = gamma_0 + 2.0 * sum((1.0 - (l / (L + 1.0))) * gammas[l - 1] for l in range(1, L + 1))
    se_hac = float(np.sqrt(max(v_hac, 1e-12) / T_dates))
    t_hac = float(mean_ic / se_hac) if se_hac > 0 else 0.0
    p_hac = float(2.0 * (1.0 - t.cdf(abs(t_hac), df=T_dates - 1)))

    return {
        "n_trading_dates": T_dates,
        "mean_daily_ic": mean_ic,
        "daily_ic_std": std_ic,
        "information_ratio": ir_ic,
        "newey_west_hac_se": se_hac,
        "newey_west_hac_tstat": t_hac,
        "newey_west_hac_pvalue": p_hac,
        "inference_note": "Newey-West HAC (L=4) adjusts for 5-session overlapping forward return autocorrelation.",
    }


def run_phase5j_evaluation():
    print("=" * 90)
    print("PHASE 5J — VALIDATED CROSS-SECTIONAL TRAINING & EVALUATION (60 COMPANIES)")
    print("=" * 90)

    output_dir = Path("data/processed/research/phase5j")
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load Data
    p_market_exp = Path("data/processed/market/phase5i_market_expansion.parquet")
    p_market_pilot = Path("data/processed/market/sp500_market_sample.parquet")
    p_sec_facts = Path("data/processed/sec/facts/pilot_financial_facts.parquet")
    p_sec_events = Path("data/processed/sec/eight_k/phase5f_8k_events.parquet")
    p_universe = Path("data/processed/universe/sp500_universe.parquet")
    p_eligibility = Path("data/processed/universe/phase5j_company_eligibility.csv")

    if not p_market_exp.exists():
        raise FileNotFoundError(f"Missing expanded market data: {p_market_exp}")
    if not p_eligibility.exists():
        raise FileNotFoundError(f"Missing eligibility manifest: {p_eligibility}")

    df_eligibility = pd.read_csv(p_eligibility)
    print(f"Loaded eligibility manifest for {len(df_eligibility)} companies.")
    eligible_60_tickers = df_eligibility["ticker"].tolist()

    df_raw_mkt = pd.read_parquet(p_market_exp)
    print(f"Loaded expanded market data: {len(df_raw_mkt):,} rows across {df_raw_mkt['ticker'].nunique()} tickers.")

    # 2. Extract Warmup & Primary Window (2018-01-01 to 2020-06-15)
    # Warmup is critical so that rolling 20d/60d features are fully populated on 2019-01-02
    sub_market = df_raw_mkt[
        (df_raw_mkt["ticker"].isin(eligible_60_tickers))
        & (df_raw_mkt["trading_date"] >= "2018-01-01")
        & (df_raw_mkt["trading_date"] <= "2020-06-15")
    ].copy()

    # Pre-derive adjusted open for exact mark-to-market portfolio pricing
    adj_factor = sub_market["adjusted_close"] / sub_market["close"]
    sub_market["adjusted_open"] = sub_market["open"] * adj_factor

    print(f"Computing market technical features on {len(sub_market):,} rows (warmed from 2018)...")
    m_engine = MarketFeatureEngine(MarketFeatureConfig(decision_timing=DecisionTimingMode.NEXT_SESSION_OPEN))
    df_features = m_engine.compute_features(sub_market)

    # 3. Add 5-Session Forward Return Target (T close -> T+1 open to T+5 close)
    print("Computing 5-session forward return targets...")
    tgt_engine = ForwardReturnTargetEngine(TargetConfig(horizon_sessions=5))
    df_with_target = tgt_engine.add_target(df_features)

    # Filter to primary research evaluation window: 2019-01-01 to 2020-06-10 and valid targets
    df_eval = df_with_target[
        (df_with_target["trading_date"] >= "2019-01-01")
        & (df_with_target["trading_date"] <= "2020-06-10")
        & (df_with_target["target_forward_return_5d_valid"] == True)
    ].copy()

    df_all = df_eval.sort_values(["trading_date", "company_id"]).reset_index(drop=True)
    n_total_valid = len(df_all)
    unique_dates = sorted(df_all["trading_date"].unique().tolist())
    print(f"Total Valid Labeled Rows: {n_total_valid:,} across {len(unique_dates)} unique calendar dates.")
    print(f"Active companies in panel: {df_all['ticker'].nunique()} tickers.")

    # 4. Set Up Chronological Walk-Forward Splitter (4 folds: min_T=173, val=45, purge=5)
    wf_cfg = WalkForwardConfig(n_splits=4, train_min_sessions=173, val_sessions=45, purge_sessions=5)
    splitter = WalkForwardSplitter(wf_cfg)

    feature_cols = MarketBaselinePipeline.MARKET_FEATURE_COLUMNS
    pipe_mkt = MarketBaselinePipeline(feature_columns=feature_cols)

    # Containers for results
    fold_eval_records = []
    oos_predictions_list = []
    company_fold_metrics = []

    print("\n" + "=" * 90)
    print("TRACK A: 60-COMPANY CROSS-SECTIONAL WALK-FORWARD EVALUATION")
    print("=" * 90)

    for fold, (tr_idx, val_idx) in enumerate(splitter.split(df_all)):
        tr_df = df_all.iloc[tr_idx].copy()
        val_df = df_all.iloc[val_idx].copy()

        y_tr = tr_df["target_forward_return_5d"].values
        y_val = val_df["target_forward_return_5d"].values

        tr_dates = sorted(tr_df["trading_date"].unique().tolist())
        val_dates = sorted(val_df["trading_date"].unique().tolist())

        # Reference 0: Naive Zero Return
        res_zero = pipe_mkt.evaluate_naive_zero(y_val)

        # Reference 1: Historical Median Return (fit on y_tr)
        res_median = pipe_mkt.evaluate_naive_median(y_tr, y_val)

        # Model 1: Cross-Sectional Ridge Regression
        res_ridge = pipe_mkt.fit_and_evaluate_ridge(
            tr_df, y_tr, val_df, y_val, model_name=f"Ridge_CrossSectional_Fold{fold}"
        )

        # Compute Directional Accuracy and IC
        pred_ridge = res_ridge.predictions
        hit_rate_ridge = compute_directional_accuracy(y_val, pred_ridge)
        ic_ridge, ic_p_ridge = compute_ic(y_val, pred_ridge)

        hit_rate_zero = compute_directional_accuracy(y_val, res_zero.predictions)
        hit_rate_median = compute_directional_accuracy(y_val, res_median.predictions)

        # Residuals for uncertainty estimation
        pipe_tr = MarketBaselinePipeline(feature_columns=feature_cols, alphas=(res_ridge.best_params["alpha"],))
        res_tr_eval = pipe_tr.fit_and_evaluate_ridge(tr_df, y_tr, tr_df, y_tr, model_name=f"TrEval_Fold{fold}")
        tr_residuals = y_tr - res_tr_eval.predictions
        sigma_train = float(np.std(tr_residuals, ddof=1))

        # Record out-of-sample predictions
        val_df_records = val_df.copy()
        val_df_records["predicted_return"] = pred_ridge
        val_df_records["target_return"] = y_val
        val_df_records["residual"] = y_val - pred_ridge
        val_df_records["fold"] = fold
        val_df_records["alpha"] = res_ridge.best_params["alpha"]
        val_df_records["sigma_train"] = sigma_train
        oos_predictions_list.append(val_df_records)

        # Per-company breakdown within fold
        for tk, comp_grp in val_df_records.groupby("ticker"):
            c_y_true = comp_grp["target_return"].values
            c_y_pred = comp_grp["predicted_return"].values
            c_mae = float(np.mean(np.abs(c_y_true - c_y_pred)))
            c_rmse = float(np.sqrt(np.mean((c_y_true - c_y_pred) ** 2)))
            c_hit = compute_directional_accuracy(c_y_true, c_y_pred)
            c_ic, _ = compute_ic(c_y_true, c_y_pred)
            company_fold_metrics.append({
                "fold": fold,
                "ticker": tk,
                "n_obs": len(comp_grp),
                "mae": c_mae,
                "rmse": c_rmse,
                "hit_rate": c_hit,
                "ic": c_ic,
            })

        val_companies = sorted(val_df["ticker"].unique().tolist())
        print(f"\n--- FOLD {fold} (Val: {val_dates[0]} -> {val_dates[-1]}, N={len(val_df):,}, {len(val_companies)} companies) ---")
        print(f"  Train Sessions : {len(tr_dates)} sessions ({tr_dates[0]} -> {tr_dates[-1]}), N={len(tr_df):,}")
        print(f"  Best Alpha     : {res_ridge.best_params['alpha']:.2f}")
        print(f"  Train Sigma    : {sigma_train:.4f}")
        print(f"  Ref 0 (Zero)   : RMSE = {res_zero.rmse:.4f}, MAE = {res_zero.mae:.4f}")
        print(f"  Ref 1 (Median) : RMSE = {res_median.rmse:.4f}, MAE = {res_median.mae:.4f}, Median = {np.median(y_tr):.4f}")
        print(f"  Ridge Model    : RMSE = {res_ridge.rmse:.4f}, MAE = {res_ridge.mae:.4f}, Hit Rate = {hit_rate_ridge*100:.1f}%, IC = {ic_ridge:.3f}")

        fold_eval_records.append({
            "fold": fold,
            "train_sessions": len(tr_dates),
            "val_sessions": len(val_dates),
            "train_start_date": tr_dates[0],
            "train_end_date": tr_dates[-1],
            "val_start_date": val_dates[0],
            "val_end_date": val_dates[-1],
            "n_train_obs": len(tr_df),
            "n_val_obs": len(val_df),
            "n_val_companies": len(val_companies),
            "val_companies": val_companies,
            "best_alpha": float(res_ridge.best_params["alpha"]),
            "sigma_train": float(sigma_train),
            "metrics": {
                "zero_baseline": {
                    "rmse": float(res_zero.rmse),
                    "mae": float(res_zero.mae),
                    "bias": float(np.mean(res_zero.predictions - y_val)),
                    "hit_rate": float(hit_rate_zero),
                },
                "median_baseline": {
                    "rmse": float(res_median.rmse),
                    "mae": float(res_median.mae),
                    "bias": float(np.mean(res_median.predictions - y_val)),
                    "hit_rate": float(hit_rate_median),
                },
                "ridge_cross_sectional": {
                    "rmse": float(res_ridge.rmse),
                    "mae": float(res_ridge.mae),
                    "bias": float(np.mean(res_ridge.predictions - y_val)),
                    "hit_rate": float(hit_rate_ridge),
                    "ic": float(ic_ridge),
                    "ic_pvalue": float(ic_p_ridge),
                },
            },
        })

    # Combine all out-of-sample predictions
    df_all_oos = pd.concat(oos_predictions_list, ignore_index=True)
    y_true_all = df_all_oos["target_return"].values
    y_pred_all = df_all_oos["predicted_return"].values

    agg_rmse = float(np.sqrt(np.mean((y_true_all - y_pred_all) ** 2)))
    agg_mae = float(np.mean(np.abs(y_true_all - y_pred_all)))
    agg_bias = float(np.mean(y_pred_all - y_true_all))
    agg_hit_rate = compute_directional_accuracy(y_true_all, y_pred_all)
    agg_ic, agg_ic_p = compute_ic(y_true_all, y_pred_all)
    daily_cs_ic = compute_daily_cross_sectional_ic(df_all_oos)

    # Aggregate baselines
    zero_rmse = float(np.sqrt(np.mean(y_true_all ** 2)))
    zero_mae = float(np.mean(np.abs(y_true_all)))

    print("\n" + "=" * 90)
    print(f"TRACK A OVERALL OUT-OF-SAMPLE RESULTS (N = {len(df_all_oos):,} Observations)")
    print("=" * 90)
    print(f"{'Model':<30} {'RMSE':<10} {'MAE':<10} {'Bias':<10} {'Hit Rate':<12} {'Rank IC'}")
    print("-" * 80)
    print(f"{'Reference 0 (Zero Return)':<30} {zero_rmse:<10.4f} {zero_mae:<10.4f} {0.0:<10.4f} {'50.0%':<12} {'0.000'}")
    print(f"{'Cross-Sectional Ridge (60 Co)':<30} {agg_rmse:<10.4f} {agg_mae:<10.4f} {agg_bias:<10.4f} {f'{agg_hit_rate*100:.1f}%':<12} {f'{agg_ic:.3f} (Exploratory p={agg_ic_p:.2e})'}")
    print(f"  --> Daily Cross-Sectional IC ({daily_cs_ic['n_trading_dates']} dates): Mean={daily_cs_ic['mean_daily_ic']:+.4f}, Std={daily_cs_ic['daily_ic_std']:.4f}, IR={daily_cs_ic['information_ratio']:+.3f}")
    print(f"  --> Newey-West HAC (L=4) Inference : t={daily_cs_ic['newey_west_hac_tstat']:+.3f}, p={daily_cs_ic['newey_west_hac_pvalue']:.4f}")

    # Save out-of-sample predictions parquet
    oos_save_cols = [
        "trading_date", "company_id", "ticker", "fold",
        "target_return", "predicted_return", "residual",
        "market_volatility_5d", "adjusted_open", "close", "adjusted_close",
        "alpha", "sigma_train",
    ]
    df_all_oos[oos_save_cols].to_parquet(output_dir / "phase5j_predictions_track_a.parquet", index=False)
    print(f"\nSaved out-of-sample predictions to {output_dir / 'phase5j_predictions_track_a.parquet'}")

    # 5. Multi-Track Comparison on Common Subset (Tracks A, B, C, D on AAPL, JPM, GOOG, TSLA)
    print("\n" + "=" * 90)
    print("MULTI-TRACK COMPARISON ON COMMON PILOT COHORT (AAPL, JPM, GOOG, TSLA - N = 720)")
    print("=" * 90)

    # Build multi-modal dataset for the 4 core pilot tickers
    df_pilot_mkt = pd.read_parquet(p_market_pilot)
    df_facts = pd.read_parquet(p_sec_facts) if p_sec_facts.exists() else None
    df_events = pd.read_parquet(p_sec_events) if p_sec_events.exists() else None
    df_univ = pd.read_parquet(p_universe)

    core_cids = ["US_CIK_0000320193", "US_CIK_0000019617", "US_CIK_0001652044", "US_CIK_0001318605"]
    sub_pilot_mkt = df_pilot_mkt[
        (df_pilot_mkt["company_id"].isin(core_cids))
        & (df_pilot_mkt["trading_date"] >= "2019-01-01")
        & (df_pilot_mkt["trading_date"] <= "2020-06-10")
    ].copy()

    sub_pilot_mkt = tgt_engine.add_target(sub_pilot_mkt)

    b_cfg = DatasetBuildConfig(
        market_config=MarketFeatureConfig(decision_timing=DecisionTimingMode.NEXT_SESSION_OPEN),
        pre_open_cutoff_minutes=15,
    )
    pilot_builder = UnifiedDatasetBuilder(b_cfg)
    pilot_res = pilot_builder.build_dataset(
        df_market=sub_pilot_mkt,
        df_fundamentals=df_facts,
        universe_df=df_univ,
        df_events=df_events,
    )

    df_pilot_unified = pilot_res.data[pilot_res.data["target_forward_return_5d_valid"]].copy()
    df_pilot_all = df_pilot_unified.sort_values(["trading_date", "company_id"]).reset_index(drop=True)

    mkt_cols = MarketBaselinePipeline.MARKET_FEATURE_COLUMNS
    fund_cols = MarketBaselinePipeline.FUNDAMENTAL_FEATURE_COLUMNS
    evt_cols = MarketBaselinePipeline.EVENT_FEATURE_COLUMNS

    track_pipelines = {
        "Track A (Market-Only)": MarketBaselinePipeline(feature_columns=mkt_cols),
        "Track B (Market + Fundamentals)": MarketBaselinePipeline(feature_columns=mkt_cols + fund_cols),
        "Track C (Market + Filing Events)": MarketBaselinePipeline(feature_columns=mkt_cols + evt_cols),
        "Track D (Combined Multi-Modal)": MarketBaselinePipeline(feature_columns=mkt_cols + fund_cols + evt_cols),
    }

    track_results = {name: [] for name in track_pipelines}
    track_y_val_all = []

    for f_idx, (p_tr_idx, p_val_idx) in enumerate(splitter.split(df_pilot_all)):
        p_tr_df = df_pilot_all.iloc[p_tr_idx]
        p_val_df = df_pilot_all.iloc[p_val_idx]
        p_y_tr = p_tr_df["target_forward_return_5d"].values
        p_y_val = p_val_df["target_forward_return_5d"].values
        track_y_val_all.extend(p_y_val)

        for t_name, pipe in track_pipelines.items():
            r = pipe.fit_and_evaluate_ridge(p_tr_df, p_y_tr, p_val_df, p_y_val, model_name=f"{t_name}_Fold{f_idx}")
            track_results[t_name].extend(r.predictions)

    track_y_true = np.array(track_y_val_all)
    track_comparison_summary = {}

    print(f"{'Track Name':<35} {'N Obs':<8} {'RMSE':<10} {'MAE':<10} {'Hit Rate':<12} {'Rank IC'}")
    print("-" * 85)

    for t_name, preds_list in track_results.items():
        preds_arr = np.array(preds_list)
        t_rmse = float(np.sqrt(np.mean((track_y_true - preds_arr) ** 2)))
        t_mae = float(np.mean(np.abs(track_y_true - preds_arr)))
        t_hit = compute_directional_accuracy(track_y_true, preds_arr)
        t_ic, t_p = compute_ic(track_y_true, preds_arr)

        track_comparison_summary[t_name] = {
            "n_observations": len(track_y_true),
            "rmse": t_rmse,
            "mae": t_mae,
            "hit_rate": t_hit,
            "rank_ic": t_ic,
            "rank_ic_pvalue": t_p,
            "eligibility_scope": "Common 4-Company Cohort (AAPL, JPM, GOOG, TSLA)",
        }
        print(f"{t_name:<35} {len(track_y_true):<8} {t_rmse:<10.4f} {t_mae:<10.4f} {f'{t_hit*100:.1f}%':<12} {f'{t_ic:.3f} (p={t_p:.2e})'}")

    # 6. Cross-Sectional Decision & Risk Layer Evaluation
    print("\n" + "=" * 90)
    print("CROSS-SECTIONAL DECISION LAYER & PORTFOLIO SIMULATION (60 COMPANIES)")
    print("=" * 90)

    # Configure costs: 15 bps round-trip friction
    cost_cfg = TransactionCostConfig(
        entry_fee_bps=2.5,
        exit_fee_bps=2.5,
        half_spread_bps=2.5,
        slippage_bps=2.5,
    )

    # We evaluate two policies: Fixed 1.5% hurdle and Rolling/Adaptive hurdle
    risk_cfg_fixed = RiskGateConfig(
        buy_threshold=0.015,
        sell_threshold=-0.015,
        max_uncertainty=0.08,
        min_net_return_hurdle=0.005,
        enforce_uncertainty_gate=True,
    )

    decisions_list = []
    signals_count = {"BUY": 0, "HOLD": 0, "SELL": 0}

    # Evaluate decisions on all 10,574 out-of-sample predictions
    for idx in range(len(df_all_oos)):
        row = df_all_oos.iloc[idx]
        tk = row["ticker"]
        cid = row["company_id"]
        d_date = row["trading_date"]
        pred = row["predicted_return"]
        fld = row["fold"]
        sig = row["sigma_train"]
        vol_5d = row.get("market_volatility_5d")

        # Use residual uncertainty estimator instance
        u_estimator = ResidualUncertaintyEstimator(
            residual_std=float(sig), method_name="fold_training_sigma"
        )
        policy = ThresholdDecisionPolicy(uncertainty_estimator=u_estimator)

        req = DecisionContractRequest(
            company_id=cid,
            ticker=tk,
            decision_timestamp=f"{d_date}T14:15:00Z",
            predicted_forward_return=float(pred),
            forecast_uncertainty=float(sig),
            rolling_volatility_5d=float(vol_5d) if pd.notna(vol_5d) else None,
            feature_metadata={"n_features_used": len(feature_cols), "n_features_required": len(feature_cols)},
            model_id=f"Ridge_CrossSectional_Fold{fld}",
            training_cutoff_date=fold_eval_records[fld]["train_end_date"],
            cost_config=cost_cfg,
            risk_config=risk_cfg_fixed,
        )

        resp = policy.evaluate(req)
        sig_str = resp.signal.value
        signals_count[sig_str] += 1

        decisions_list.append({
            "trading_date": d_date,
            "ticker": tk,
            "company_id": cid,
            "signal": sig_str,
            "expected_net_return": resp.expected_net_return,
            "predicted_forward_return": float(pred),
            "forecast_uncertainty": float(sig),
            "fold": fld,
        })

    df_decisions = pd.DataFrame(decisions_list)
    print(f"Decision Policy Distribution across 10,574 Out-of-Sample Predictions:")
    print(f"  BUY  : {signals_count['BUY']:,} ({signals_count['BUY']/len(df_all_oos)*100:.2f}%)")
    print(f"  HOLD : {signals_count['HOLD']:,} ({signals_count['HOLD']/len(df_all_oos)*100:.2f}%)")
    print(f"  SELL : {signals_count['SELL']:,} ({signals_count['SELL']/len(df_all_oos)*100:.2f}%)")

    # 7. Institutional Portfolio Simulation on 60-Company Universe
    # Parameters for cross-sectional portfolio:
    # 10 max concurrent positions, 10% target weight per position, $100,000 cash, 15 bps friction, 5-session horizon
    port_cfg_cs = PortfolioConfig(
        initial_cash=100_000.0,
        max_concurrent_positions=10,
        max_position_weight=0.10,
        max_aggregate_exposure=1.0,
        holding_horizon_sessions=5,
        allow_multiple_positions_per_ticker=False,
        cost_config=cost_cfg,
    )

    val_dates_all = sorted(df_decisions["trading_date"].unique().tolist())
    min_val_date = val_dates_all[0]
    market_sim_df = sub_market[
        (sub_market["trading_date"] >= min_val_date)
        & (sub_market["trading_date"] <= "2020-06-15")
    ].copy()

    sim = DeterministicPortfolioSimulator(port_cfg_cs)
    sim_result = sim.simulate(
        decisions_df=df_decisions,
        market_df=market_sim_df,
        strategy_name="Phase 5J Cross-Sectional Ridge Portfolio (60 Companies)",
    )

    # Benchmark: Cash ($100k, 0 return)
    # Benchmark: Equal-Weight Buy-and-Hold across all 60 companies
    sim_dates = [s.date for s in sim_result.daily_history]
    first_date = sim_dates[0]
    bh_first_candidates = sorted(df_all[df_all["trading_date"] == first_date]["ticker"].unique().tolist())
    bh_weight = 1.0 / len(bh_first_candidates) if bh_first_candidates else 0.02

    bh_decisions = pd.DataFrame([
        {
            "trading_date": first_date,
            "ticker": tk,
            "company_id": df_all[df_all["ticker"] == tk]["company_id"].iloc[0],
            "signal": "BUY",
        }
        for tk in bh_first_candidates
    ])

    port_cfg_bh = PortfolioConfig(
        initial_cash=100_000.0,
        max_concurrent_positions=len(bh_first_candidates),
        max_position_weight=bh_weight,
        max_aggregate_exposure=1.0,
        holding_horizon_sessions=len(sim_dates),
        cost_config=cost_cfg,
    )
    sim_bh = DeterministicPortfolioSimulator(port_cfg_bh).simulate(
        decisions_df=bh_decisions,
        market_df=market_sim_df,
        strategy_name="Equal-Weight Buy & Hold (60-Company Cohort)",
    )

    print("\n" + "=" * 90)
    print("PORTFOLIO SIMULATION RESULTS (60 COMPANIES, 10 POSITIONS CAP, 15 BPS FRICTION)")
    print("=" * 90)
    print(f"{'Metric':<35} {'Cash Benchmark':<18} {'Equal-Weight B&H':<20} {'Cross-Sectional Policy'}")
    print("-" * 90)
    print(f"{'Initial Equity':<35} {'$100,000.00':<18} {'$100,000.00':<20} {'$100,000.00'}")
    print(f"{'Final Equity':<35} {'$100,000.00':<18} {f'${sim_bh.final_equity:,.2f}':<20} {f'${sim_result.final_equity:,.2f}'}")
    print(f"{'Total Net Return':<35} {'0.00%':<18} {f'{sim_bh.total_net_return*100:+.2f}%':<20} {f'{sim_result.total_net_return*100:+.2f}%'}")
    print(f"{'Annualized Return':<35} {'0.00%':<18} {f'{sim_bh.annualized_return*100:+.2f}%':<20} {f'{sim_result.annualized_return*100:+.2f}%'}")
    print(f"{'Max Drawdown':<35} {'0.00%':<18} {f'{sim_bh.max_drawdown*100:.2f}%':<20} {f'{sim_result.max_drawdown*100:.2f}%'}")
    print(f"{'Daily Volatility (Ann.)':<35} {'0.00%':<18} {f'{sim_bh.daily_volatility*100:.2f}%':<20} {f'{sim_result.daily_volatility*100:.2f}%'}")
    print(f"{'Sharpe Ratio (Rf=0%)':<35} {'0.00':<18} {f'{sim_bh.sharpe_ratio:.2f}':<20} {f'{sim_result.sharpe_ratio:.2f}'}")
    print(f"{'Total Closed Trades':<35} {'0':<18} {f'{sim_bh.total_closed_trades}':<20} {f'{sim_result.total_closed_trades}'}")
    print(f"{'Win Rate on Closed Trades':<35} {'N/A':<18} {f'{sim_bh.win_rate*100:.1f}%':<20} {f'{sim_result.win_rate*100:.1f}%'}")
    print(f"{'Mean Net Return / Trade':<35} {'N/A':<18} {f'{sim_bh.mean_net_return_per_trade*100:+.2f}%':<20} {f'{sim_result.mean_net_return_per_trade*100:+.2f}%'}")
    print(f"{'Total Transaction Costs':<35} {'$0.00':<18} {f'${sim_bh.total_transaction_costs:,.2f}':<20} {f'${sim_result.total_transaction_costs:,.2f}'}")
    print(f"{'Total Rejected Orders':<35} {'0':<18} {'0':<20} {f'{sim_result.total_rejected_orders}'}")
    print(f"{'Average Capital Utilization':<35} {'0.0%':<18} {f'{sim_bh.average_utilization*100:.1f}%':<20} {f'{sim_result.average_utilization*100:.1f}%'}")

    if sim_result.rejection_breakdown:
        print("\nOrder Rejection Reasons:")
        for r_reason, count in sim_result.rejection_breakdown.items():
            print(f"  - {r_reason}: {count} orders")

    # 8. Save All JSON Artifacts
    phase5j_eval_artifact = {
        "metadata": {
            "experiment": "Phase 5J — Validated Cross-Sectional Training, Evaluation & Research UI",
            "contract_version": "5J.1.0",
            "evaluation_timestamp": datetime.now(timezone.utc).isoformat(),
            "date_range": "2019-01-02 to 2020-06-10",
            "n_companies_total": 60,
            "n_companies_scored_folds_0_2": 60,
            "n_companies_scored_fold_3": 55,
            "truncated_companies_fold_3": ["BLK", "CSCO", "CVS", "EQIX", "FCX"],
            "total_out_of_sample_observations": len(df_all_oos),
            "walk_forward_splits": 4,
            "purge_gap_sessions": 5,
            "target_horizon_sessions": 5,
            "target_definition": "Decision at T close -> Entry at T+1 open -> Exit at T+5 close",
            "cost_friction_bps": 15.0,
        },
        "aggregate_metrics": {
            "reference_0_zero": {
                "rmse": zero_rmse,
                "mae": zero_mae,
                "bias": 0.0,
                "hit_rate": 0.50,
            },
            "ridge_cross_sectional": {
                "rmse": agg_rmse,
                "mae": agg_mae,
                "bias": agg_bias,
                "hit_rate": agg_hit_rate,
                "rank_ic": agg_ic,
                "rank_ic_pvalue": agg_ic_p,
                "rank_ic_pooled_descriptive": agg_ic,
                "rank_ic_pooled_pvalue_exploratory": agg_ic_p,
                "daily_cross_sectional_ic": daily_cs_ic,
            },
        },
        "fold_results": fold_eval_records,
        "company_summary": {
            "n_companies": len(df_eligibility),
            "sectors": df_eligibility["sector"].value_counts().to_dict(),
            "coverage_counts": {
                "eligible_all_folds": 54,
                "eligible_with_bmy_offset": 1,
                "truncated_2020_04_01": 5,
            },
        },
        "portfolio_simulation": {
            "cash_benchmark": {
                "initial_equity": 100000.0,
                "final_equity": 100000.0,
                "total_net_return": 0.0,
                "max_drawdown": 0.0,
                "sharpe_ratio": 0.0,
            },
            "buy_and_hold_benchmark": {
                "initial_equity": 100000.0,
                "final_equity": sim_bh.final_equity,
                "total_net_return": sim_bh.total_net_return,
                "annualized_return": sim_bh.annualized_return,
                "max_drawdown": sim_bh.max_drawdown,
                "sharpe_ratio": sim_bh.sharpe_ratio,
                "daily_volatility": sim_bh.daily_volatility,
            },
            "cross_sectional_policy": {
                "initial_equity": 100000.0,
                "final_equity": sim_result.final_equity,
                "total_net_return": sim_result.total_net_return,
                "annualized_return": sim_result.annualized_return,
                "max_drawdown": sim_result.max_drawdown,
                "daily_volatility": sim_result.daily_volatility,
                "sharpe_ratio": sim_result.sharpe_ratio,
                "total_closed_trades": sim_result.total_closed_trades,
                "win_rate": sim_result.win_rate,
                "mean_net_return_per_trade": sim_result.mean_net_return_per_trade,
                "total_transaction_costs": sim_result.total_transaction_costs,
                "total_rejected_orders": sim_result.total_rejected_orders,
                "average_utilization": sim_result.average_utilization,
                "rejection_breakdown": sim_result.rejection_breakdown,
                "signal_counts": signals_count,
            },
        },
    }

    with open(output_dir / "phase5j_cross_sectional_evaluation_results.json", "w", encoding="utf-8") as f:
        json.dump(phase5j_eval_artifact, f, indent=2)

    with open(output_dir / "phase5j_track_comparison.json", "w", encoding="utf-8") as f:
        json.dump(track_comparison_summary, f, indent=2)

    print(f"\nWrote artifacts to:")
    print(f"  - {output_dir / 'phase5j_cross_sectional_evaluation_results.json'}")
    print(f"  - {output_dir / 'phase5j_track_comparison.json'}")
    print(f"  - {output_dir / 'phase5j_predictions_track_a.parquet'}")

    return phase5j_eval_artifact


if __name__ == "__main__":
    run_phase5j_evaluation()

"""
Phase 5H — Portfolio Simulation & Leakage-Safe Threshold Validation Evaluation Script.

Evaluates:
1. Leakage-safe rolling chronological threshold selection across walk-forward folds.
2. Institutional portfolio simulation under explicit capital, concurrent position, and allocation constraints.
3. Realistic mark-to-market portfolio accounting with 15 bps round-trip transaction friction.
4. Comprehensive comparison against Cash and Equal-Weight Buy-and-Hold baselines.
5. Stress testing across transaction cost levels (5, 15, 30 bps), position caps, and concurrent limits.
"""

import json
from pathlib import Path
from typing import Dict, List, Any
import numpy as np
import pandas as pd

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


def run_phase5h_evaluation():
    print("=" * 85)
    print("PHASE 5H — PORTFOLIO SIMULATION & LEAKAGE-SAFE THRESHOLD VALIDATION")
    print("=" * 85)

    # 1. Load Datasets
    p_market = Path("data/processed/market/sp500_market_sample.parquet")
    p_sec_facts = Path("data/processed/sec/facts/pilot_financial_facts.parquet")
    p_sec_events = Path("data/processed/sec/eight_k/phase5f_8k_events.parquet")
    p_universe = Path("data/processed/universe/sp500_universe.parquet")

    df_market = pd.read_parquet(p_market)
    df_sec_facts = pd.read_parquet(p_sec_facts) if p_sec_facts.exists() else None
    df_sec_events = pd.read_parquet(p_sec_events) if p_sec_events.exists() else None
    df_universe = pd.read_parquet(p_universe)

    # Filter to 4 verified companies in 2019-01-01 to 2020-06-10 window
    sub_market = df_market[
        (df_market["ticker"].isin(["AAPL", "JPM", "GOOG", "TSLA"]))
        & (df_market["trading_date"] >= "2019-01-01")
        & (df_market["trading_date"] <= "2020-06-10")
    ].copy()

    # Pre-derive adjusted open for exact portfolio pricing
    adj_factor = sub_market["adjusted_close"] / sub_market["close"]
    sub_market["adjusted_open"] = sub_market["open"] * adj_factor

    # 2. Add Target (H = 5 forward return)
    target_engine = ForwardReturnTargetEngine(TargetConfig(horizon_sessions=5))
    sub_market = target_engine.add_target(sub_market)

    # 3. Build Unified Dataset
    m_cfg = MarketFeatureConfig(decision_timing=DecisionTimingMode.NEXT_SESSION_OPEN)
    cfg = DatasetBuildConfig(market_config=m_cfg, pre_open_cutoff_minutes=15)
    builder = UnifiedDatasetBuilder(cfg)
    res = builder.build_dataset(
        df_market=sub_market,
        df_fundamentals=df_sec_facts,
        universe_df=df_universe,
        df_events=df_sec_events,
    )

    df_unified = res.data[res.data["target_forward_return_5d_valid"]].copy()
    df_all = df_unified.sort_values(["trading_date", "company_id"]).reset_index(drop=True)

    print(f"Total Aligned Labeled Rows: {len(df_all)} across {df_all['trading_date'].nunique()} unique calendar dates.")
    print(f"Companies: {df_all['ticker'].unique().tolist()}")

    # 4. Walk-Forward Setup (4 folds: min_T=173, val=45, purge=5)
    wf_cfg = WalkForwardConfig(n_splits=4, train_min_sessions=173, val_sessions=45, purge_sessions=5)
    splitter = WalkForwardSplitter(wf_cfg)

    feature_cols = MarketBaselinePipeline.MARKET_FEATURE_COLUMNS
    pipe_mkt = MarketBaselinePipeline(feature_columns=feature_cols)

    # Base Portfolio & Cost Config
    base_cost_cfg = TransactionCostConfig(
        entry_fee_bps=2.5,
        exit_fee_bps=2.5,
        half_spread_bps=2.5,
        slippage_bps=2.5,  # 15.0 bps total round-trip
    )
    port_cfg = PortfolioConfig(
        initial_cash=100_000.0,
        max_concurrent_positions=4,
        max_position_weight=0.25,
        max_aggregate_exposure=1.0,
        holding_horizon_sessions=5,
        allow_multiple_positions_per_ticker=False,
        cost_config=base_cost_cfg,
    )

    threshold_selector = RollingThresholdSelector(
        RollingThresholdConfig(
            candidate_thresholds=[0.005, 0.010, 0.015, 0.020, 0.030],
            inner_val_sessions=45,
            inner_purge_sessions=5,
            min_inner_trades=3,
            fallback_threshold=0.015,
        )
    )

    rolling_threshold_records: List[RollingThresholdResult] = []
    fixed_decisions_all: List[Dict[str, Any]] = []
    rolling_decisions_all: List[Dict[str, Any]] = []
    fold_summaries: List[Dict[str, Any]] = []

    print("\n" + "=" * 85)
    print("CHRONOLOGICAL WALK-FORWARD FOLDS & ROLLING THRESHOLD SELECTION")
    print("=" * 85)

    for fold, (tr_idx, val_idx) in enumerate(splitter.split(df_all)):
        tr_df = df_all.iloc[tr_idx].copy()
        val_df = df_all.iloc[val_idx].copy()

        y_tr = tr_df["target_forward_return_5d"].values
        y_val = val_df["target_forward_return_5d"].values

        tr_dates = sorted(tr_df["trading_date"].unique().tolist())
        val_dates = sorted(val_df["trading_date"].unique().tolist())

        # Fit model on outer training fold
        res_mkt = pipe_mkt.fit_and_evaluate_ridge(tr_df, y_tr, val_df, y_val, model_name=f"Ridge_Fold{fold}")

        # Derive training residuals for uncertainty estimation
        pipe_tr = MarketBaselinePipeline(feature_columns=feature_cols, alphas=(res_mkt.best_params["alpha"],))
        res_tr_eval = pipe_tr.fit_and_evaluate_ridge(tr_df, y_tr, tr_df, y_tr, model_name=f"TrainEval_Fold{fold}")
        train_resids = y_tr - res_tr_eval.predictions
        uncertainty_estimator = ResidualUncertaintyEstimator(
            training_residuals=train_resids, method_name="training_residual_std"
        )
        sigma_train = uncertainty_estimator.get_uncertainty()

        # Step 1: Leakage-Safe Rolling Threshold Selection using ONLY tr_df
        th_result = threshold_selector.select_threshold_for_fold(
            outer_fold=fold,
            df_train_outer=tr_df,
            feature_columns=feature_cols,
            base_cost_cfg=base_cost_cfg,
            max_uncertainty=0.08,
        )
        rolling_threshold_records.append(th_result)
        selected_th = th_result.selected_threshold

        print(f"\n--- FOLD {fold} (Val: {val_dates[0]} -> {val_dates[-1]}, N={len(val_df)}) ---")
        print(f"  Training Dates: {tr_dates[0]} -> {tr_dates[-1]} ({len(tr_dates)} sessions)")
        print(f"  Uncertainty Sigma: {sigma_train:.4f}")
        print(f"  Rolling Threshold Selected: {selected_th*100:.1f}% (Fallback: {th_result.fallback_used})")
        if th_result.fallback_used:
            print(f"    --> Fallback Reason: {th_result.fallback_reason}")

        # Policies for this fold: Fixed (1.5%) vs Rolling
        policy_fixed = ThresholdDecisionPolicy(uncertainty_estimator=uncertainty_estimator)
        policy_rolling = ThresholdDecisionPolicy(uncertainty_estimator=uncertainty_estimator)

        risk_cfg_fixed = RiskGateConfig(
            buy_threshold=0.015,
            sell_threshold=-0.015,
            max_uncertainty=0.08,
            min_net_return_hurdle=0.005,
            enforce_uncertainty_gate=True,
        )
        risk_cfg_rolling = RiskGateConfig(
            buy_threshold=selected_th,
            sell_threshold=-selected_th,
            max_uncertainty=0.08,
            min_net_return_hurdle=0.005,
            enforce_uncertainty_gate=True,
        )

        val_preds = res_mkt.predictions
        f_signals_fixed = []
        f_signals_rolling = []

        for j in range(len(val_df)):
            row = val_df.iloc[j]
            pred = val_preds[j]
            tk = row["ticker"]
            cid = row["company_id"]
            d_date = row["trading_date"]
            vol_5d = row.get("market_volatility_5d")

            # Common request attributes
            req_base = {
                "company_id": cid,
                "ticker": tk,
                "decision_timestamp": f"{d_date}T14:15:00Z",
                "predicted_forward_return": pred,
                "forecast_uncertainty": sigma_train,
                "rolling_volatility_5d": float(vol_5d) if pd.notna(vol_5d) else None,
                "feature_metadata": {"n_features_used": len(feature_cols), "n_features_required": len(feature_cols)},
                "model_id": f"Ridge_Fold{fold}",
                "training_cutoff_date": tr_dates[-1],
                "cost_config": base_cost_cfg,
            }

            # 1. Fixed Policy Decision
            req_fix = DecisionContractRequest(**req_base, risk_config=risk_cfg_fixed)
            resp_fix = policy_fixed.evaluate(req_fix)
            fixed_decisions_all.append({
                "trading_date": d_date,
                "ticker": tk,
                "company_id": cid,
                "signal": resp_fix.signal.value,
                "expected_net_return": resp_fix.expected_net_return,
                "fold": fold,
            })
            f_signals_fixed.append(resp_fix.signal.value)

            # 2. Rolling Policy Decision
            req_roll = DecisionContractRequest(**req_base, risk_config=risk_cfg_rolling)
            resp_roll = policy_rolling.evaluate(req_roll)
            rolling_decisions_all.append({
                "trading_date": d_date,
                "ticker": tk,
                "company_id": cid,
                "signal": resp_roll.signal.value,
                "expected_net_return": resp_roll.expected_net_return,
                "fold": fold,
            })
            f_signals_rolling.append(resp_roll.signal.value)

        n_buy_fix = f_signals_fixed.count("BUY")
        n_buy_roll = f_signals_rolling.count("BUY")
        print(f"  Fixed 1.5% Policy Signals : BUY={n_buy_fix:>2}, SELL= 0, HOLD={len(val_df) - n_buy_fix:>3}")
        print(f"  Rolling Policy Signals    : BUY={n_buy_roll:>2}, SELL= 0, HOLD={len(val_df) - n_buy_roll:>3}")

        fold_summaries.append({
            "fold": fold,
            "train_sessions": len(tr_dates),
            "val_sessions": len(val_dates),
            "val_rows": len(val_df),
            "sigma_train": float(sigma_train),
            "selected_threshold": float(selected_th),
            "fallback_used": th_result.fallback_used,
            "fixed_buys": n_buy_fix,
            "rolling_buys": n_buy_roll,
        })

    df_decisions_fixed = pd.DataFrame(fixed_decisions_all)
    df_decisions_rolling = pd.DataFrame(rolling_decisions_all)

    # 5. Execute Portfolio Simulations across Full Out-of-Sample Window
    print("\n" + "=" * 85)
    print("PORTFOLIO SIMULATIONS: RECONCILIATION & STRATEGY COMPARISON")
    print("=" * 85)

    simulator = DeterministicPortfolioSimulator(port_cfg)

    # Run Fixed Threshold Policy Portfolio Simulation
    sim_fixed = simulator.simulate(
        decisions_df=df_decisions_fixed,
        market_df=sub_market,
        strategy_name="Phase 5G Fixed Threshold (1.5%) Portfolio",
    )

    # Run Rolling Threshold Policy Portfolio Simulation
    sim_rolling = simulator.simulate(
        decisions_df=df_decisions_rolling,
        market_df=sub_market,
        strategy_name="Phase 5H Rolling Threshold Portfolio",
    )

    # Build Buy-and-Hold Benchmark across the same calendar sessions
    sim_sessions = [s.date for s in sim_fixed.daily_history]
    bh_market = sub_market[sub_market["trading_date"].isin(sim_sessions)].copy()
    bh_first_date = sim_sessions[0]
    bh_decisions = pd.DataFrame([
        {"trading_date": bh_first_date, "ticker": "AAPL", "company_id": "US_CIK_0000320193", "signal": "BUY"},
        {"trading_date": bh_first_date, "ticker": "JPM", "company_id": "US_CIK_0000019617", "signal": "BUY"},
        {"trading_date": bh_first_date, "ticker": "GOOG", "company_id": "US_CIK_0001652044", "signal": "BUY"},
        {"trading_date": bh_first_date, "ticker": "TSLA", "company_id": "US_CIK_0001318605", "signal": "BUY"},
    ])
    # Buy and hold indefinitely across evaluation period
    cfg_bh = PortfolioConfig(
        initial_cash=100_000.0,
        max_concurrent_positions=4,
        max_position_weight=0.25,
        holding_horizon_sessions=len(sim_sessions),  # Hold full evaluation period
        cost_config=base_cost_cfg,
    )
    sim_bh = DeterministicPortfolioSimulator(cfg_bh).simulate(
        decisions_df=bh_decisions,
        market_df=sub_market,
        strategy_name="Equal-Weight Buy & Hold (4 Equities)",
    )

    # Summary Comparison Table
    print(f"\n{'Metric':<32} {'Cash Benchmark':<16} {'Equal-Weight B&H':<18} {'Fixed Policy (1.5%)':<20} {'Rolling Policy'}")
    print("-" * 105)
    print(f"{'Initial Equity ($)':<32} {'$100,000':<16} {'$100,000':<18} {'$100,000':<20} {'$100,000'}")
    print(f"{'Final Equity ($)':<32} {'$100,000.00':<16} {f'${sim_bh.final_equity:,.2f}':<18} {f'${sim_fixed.final_equity:,.2f}':<20} {f'${sim_rolling.final_equity:,.2f}'}")
    print(f"{'Total Net Return':<32} {'0.00%':<16} {f'{sim_bh.total_net_return*100:+.2f}%':<18} {f'{sim_fixed.total_net_return*100:+.2f}%':<20} {f'{sim_rolling.total_net_return*100:+.2f}%'}")
    print(f"{'Annualized Return':<32} {'0.00%':<16} {f'{sim_bh.annualized_return*100:+.2f}%':<18} {f'{sim_fixed.annualized_return*100:+.2f}%':<20} {f'{sim_rolling.annualized_return*100:+.2f}%'}")
    print(f"{'Max Drawdown':<32} {'0.00%':<16} {f'{sim_bh.max_drawdown*100:.2f}%':<18} {f'{sim_fixed.max_drawdown*100:.2f}%':<20} {f'{sim_rolling.max_drawdown*100:.2f}%'}")
    print(f"{'Daily Volatility (Ann.)':<32} {'0.00%':<16} {f'{sim_bh.daily_volatility*100:.2f}%':<18} {f'{sim_fixed.daily_volatility*100:.2f}%':<20} {f'{sim_rolling.daily_volatility*100:.2f}%'}")
    print(f"{'Sharpe Ratio (Rf=0%)':<32} {'0.00':<16} {f'{sim_bh.sharpe_ratio:.2f}':<18} {f'{sim_fixed.sharpe_ratio:.2f}':<20} {f'{sim_rolling.sharpe_ratio:.2f}'}")
    print(f"{'Closed Trades Taken':<32} {'0':<16} {f'{sim_bh.total_closed_trades}':<18} {f'{sim_fixed.total_closed_trades}':<20} {f'{sim_rolling.total_closed_trades}'}")
    print(f"{'Win Rate on Closed Trades':<32} {'N/A':<16} {f'{sim_bh.win_rate*100:.1f}%':<18} {f'{sim_fixed.win_rate*100:.1f}%':<20} {f'{sim_rolling.win_rate*100:.1f}%'}")
    print(f"{'Mean Net Return per Trade':<32} {'N/A':<16} {f'{sim_bh.mean_net_return_per_trade*100:+.2f}%':<18} {f'{sim_fixed.mean_net_return_per_trade*100:+.2f}%':<20} {f'{sim_rolling.mean_net_return_per_trade*100:+.2f}%'}")
    print(f"{'Total Transaction Costs':<32} {'$0.00':<16} {f'${sim_bh.total_transaction_costs:,.2f}':<18} {f'${sim_fixed.total_transaction_costs:,.2f}':<20} {f'${sim_rolling.total_transaction_costs:,.2f}'}")
    print(f"{'Total Rejected Orders':<32} {'0':<16} {'0':<18} {f'{sim_fixed.total_rejected_orders}':<20} {f'{sim_rolling.total_rejected_orders}'}")
    print(f"{'Avg Capital Utilization':<32} {'0.0%':<16} {f'{sim_bh.average_utilization*100:.1f}%':<18} {f'{sim_fixed.average_utilization*100:.1f}%':<20} {f'{sim_rolling.average_utilization*100:.1f}%'}")
    print(f"{'Max Capital Utilization':<32} {'0.0%':<16} {f'{sim_bh.max_utilization*100:.1f}%':<18} {f'{sim_fixed.max_utilization*100:.1f}%':<20} {f'{sim_rolling.max_utilization*100:.1f}%'}")

    # Print Rejection Reasons for Fixed Policy
    if sim_fixed.rejection_breakdown:
        print("\nFixed Policy Order Rejection Breakdown:")
        for r_reason, count in sim_fixed.rejection_breakdown.items():
            print(f"  {r_reason}: {count} orders")

    # 6. Sensitivity Analysis across Costs, Position Caps, and Concurrent Limits
    print("\n" + "=" * 85)
    print("STRESS TESTING & SENSITIVITY ANALYSIS (Fixed vs Rolling Policies)")
    print("=" * 85)

    cost_scenarios = [5.0, 15.0, 30.0]
    weight_scenarios = [0.15, 0.25, 0.50]
    concurrent_scenarios = [2, 4, 8]

    sensitivity_records = []

    # A. Cost Sensitivity (Base Weight=0.25, Max Concurrent=4)
    print("\n1. Cost Friction Sensitivity (5, 15, 30 bps round-trip):")
    for cbps in cost_scenarios:
        c_cfg = TransactionCostConfig(
            entry_fee_bps=cbps / 6.0,
            exit_fee_bps=cbps / 6.0,
            half_spread_bps=cbps / 6.0,
            slippage_bps=cbps / 6.0,
        )
        p_cfg = PortfolioConfig(
            initial_cash=100_000.0,
            max_concurrent_positions=4,
            max_position_weight=0.25,
            cost_config=c_cfg,
        )
        s_fix = DeterministicPortfolioSimulator(p_cfg).simulate(df_decisions_fixed, sub_market, "CostSens_Fixed")
        s_roll = DeterministicPortfolioSimulator(p_cfg).simulate(df_decisions_rolling, sub_market, "CostSens_Rolling")
        print(f"  {cbps:>4.1f} bps | Fixed Net Ret: {s_fix.total_net_return*100:+.2f}%, Costs: ${s_fix.total_transaction_costs:,.2f} | Rolling Net Ret: {s_roll.total_net_return*100:+.2f}%, Costs: ${s_roll.total_transaction_costs:,.2f}")
        sensitivity_records.append({
            "type": "cost_sensitivity",
            "cost_bps": cbps,
            "fixed_net_return": float(s_fix.total_net_return),
            "fixed_final_equity": float(s_fix.final_equity),
            "fixed_costs": float(s_fix.total_transaction_costs),
            "rolling_net_return": float(s_roll.total_net_return),
            "rolling_final_equity": float(s_roll.final_equity),
            "rolling_costs": float(s_roll.total_transaction_costs),
        })

    # B. Position Sizing Weight Sensitivity (Base Cost=15 bps, Max Concurrent=4)
    print("\n2. Position Sizing Weight Sensitivity (15%, 25%, 50% max weight):")
    for w in weight_scenarios:
        p_cfg = PortfolioConfig(
            initial_cash=100_000.0,
            max_concurrent_positions=4,
            max_position_weight=w,
            cost_config=base_cost_cfg,
        )
        s_fix = DeterministicPortfolioSimulator(p_cfg).simulate(df_decisions_fixed, sub_market, "WeightSens_Fixed")
        s_roll = DeterministicPortfolioSimulator(p_cfg).simulate(df_decisions_rolling, sub_market, "WeightSens_Rolling")
        print(f"  {w*100:>4.0f}% weight | Fixed Net Ret: {s_fix.total_net_return*100:+.2f}%, Max Util: {s_fix.max_utilization*100:.1f}% | Rolling Net Ret: {s_roll.total_net_return*100:+.2f}%, Max Util: {s_roll.max_utilization*100:.1f}%")
        sensitivity_records.append({
            "type": "weight_sensitivity",
            "max_weight": w,
            "fixed_net_return": float(s_fix.total_net_return),
            "fixed_final_equity": float(s_fix.final_equity),
            "fixed_max_utilization": float(s_fix.max_utilization),
            "rolling_net_return": float(s_roll.total_net_return),
            "rolling_final_equity": float(s_roll.final_equity),
            "rolling_max_utilization": float(s_roll.max_utilization),
        })

    # C. Concurrent Position Limit Sensitivity (Base Cost=15 bps, Weight=0.25)
    print("\n3. Concurrent Position Limit Sensitivity (2, 4, 8 positions):")
    for c_lim in concurrent_scenarios:
        p_cfg = PortfolioConfig(
            initial_cash=100_000.0,
            max_concurrent_positions=c_lim,
            max_position_weight=0.25,
            cost_config=base_cost_cfg,
        )
        s_fix = DeterministicPortfolioSimulator(p_cfg).simulate(df_decisions_fixed, sub_market, "ConcurSens_Fixed")
        s_roll = DeterministicPortfolioSimulator(p_cfg).simulate(df_decisions_rolling, sub_market, "ConcurSens_Rolling")
        print(f"  {c_lim:>2} positions | Fixed Net Ret: {s_fix.total_net_return*100:+.2f}%, Rejections: {s_fix.total_rejected_orders} | Rolling Net Ret: {s_roll.total_net_return*100:+.2f}%, Rejections: {s_roll.total_rejected_orders}")
        sensitivity_records.append({
            "type": "concurrent_limit_sensitivity",
            "max_concurrent": c_lim,
            "fixed_net_return": float(s_fix.total_net_return),
            "fixed_rejections": int(s_fix.total_rejected_orders),
            "rolling_net_return": float(s_roll.total_net_return),
            "rolling_rejections": int(s_roll.total_rejected_orders),
        })

    # 7. Save Machine-Readable Evaluation Artifact
    out_dir = Path("data/processed/sec/eight_k")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "phase5h_portfolio_evaluation_results.json"

    out_data = {
        "experiment_name": "Phase 5H Portfolio Simulation & Leakage-Safe Threshold Validation",
        "cohort": ["AAPL", "JPM", "GOOG", "TSLA"],
        "total_observations": len(df_all),
        "evaluation_period": f"{sim_sessions[0]} to {sim_sessions[-1]}",
        "portfolio_config": port_cfg.model_dump(),
        "fold_summaries": fold_summaries,
        "rolling_threshold_selection": [r.model_dump() for r in rolling_threshold_records],
        "strategy_results": {
            "cash_benchmark": {
                "initial_equity": 100_000.0,
                "final_equity": 100_000.0,
                "total_net_return": 0.0,
                "max_drawdown": 0.0,
                "sharpe_ratio": 0.0,
            },
            "buy_and_hold_benchmark": {
                "initial_equity": sim_bh.initial_equity,
                "final_equity": sim_bh.final_equity,
                "total_net_return": sim_bh.total_net_return,
                "annualized_return": sim_bh.annualized_return,
                "max_drawdown": sim_bh.max_drawdown,
                "daily_volatility": sim_bh.daily_volatility,
                "sharpe_ratio": sim_bh.sharpe_ratio,
                "total_costs": sim_bh.total_transaction_costs,
            },
            "fixed_threshold_policy": {
                "initial_equity": sim_fixed.initial_equity,
                "final_equity": sim_fixed.final_equity,
                "total_net_return": sim_fixed.total_net_return,
                "annualized_return": sim_fixed.annualized_return,
                "max_drawdown": sim_fixed.max_drawdown,
                "daily_volatility": sim_fixed.daily_volatility,
                "sharpe_ratio": sim_fixed.sharpe_ratio,
                "total_closed_trades": sim_fixed.total_closed_trades,
                "win_rate": sim_fixed.win_rate,
                "mean_net_return_per_trade": sim_fixed.mean_net_return_per_trade,
                "total_transaction_costs": sim_fixed.total_transaction_costs,
                "total_rejected_orders": sim_fixed.total_rejected_orders,
                "rejection_breakdown": sim_fixed.rejection_breakdown,
                "average_utilization": sim_fixed.average_utilization,
                "max_utilization": sim_fixed.max_utilization,
            },
            "rolling_threshold_policy": {
                "initial_equity": sim_rolling.initial_equity,
                "final_equity": sim_rolling.final_equity,
                "total_net_return": sim_rolling.total_net_return,
                "annualized_return": sim_rolling.annualized_return,
                "max_drawdown": sim_rolling.max_drawdown,
                "daily_volatility": sim_rolling.daily_volatility,
                "sharpe_ratio": sim_rolling.sharpe_ratio,
                "total_closed_trades": sim_rolling.total_closed_trades,
                "win_rate": sim_rolling.win_rate,
                "mean_net_return_per_trade": sim_rolling.mean_net_return_per_trade,
                "total_transaction_costs": sim_rolling.total_transaction_costs,
                "total_rejected_orders": sim_rolling.total_rejected_orders,
                "rejection_breakdown": sim_rolling.rejection_breakdown,
                "average_utilization": sim_rolling.average_utilization,
                "max_utilization": sim_rolling.max_utilization,
            },
        },
        "sensitivity_analysis": sensitivity_records,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out_data, f, indent=2)

    print(f"\nSaved Phase 5H evaluation results artifact to: {out_path}")


if __name__ == "__main__":
    run_phase5h_evaluation()

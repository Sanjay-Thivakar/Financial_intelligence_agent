"""
Audit Phase 5J.1: Reconciliation of Metrics, Rank IC, Inference, and Portfolio Accounting.
"""

import json
import sys
from pathlib import Path

# Ensure workspace root in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
from scipy.stats import spearmanr, t

from src.decision.schema import TransactionCostConfig, RiskGateConfig, DecisionContractRequest
from src.decision.uncertainty import ResidualUncertaintyEstimator
from src.decision.policy import ThresholdDecisionPolicy
from src.portfolio.schema import PortfolioConfig
from src.portfolio.simulator import DeterministicPortfolioSimulator


def audit_phase5j1():
    print("=" * 85)
    print("PHASE 5J.1 AUDIT: PREDICTION METRICS, RANK IC, AND PORTFOLIO ACCOUNTING")
    print("=" * 85)

    p_preds = Path("data/processed/research/phase5j/phase5j_predictions_track_a.parquet")
    p_results = Path("data/processed/research/phase5j/phase5j_cross_sectional_evaluation_results.json")
    p_market_exp = Path("data/processed/market/phase5i_market_expansion.parquet")

    assert p_preds.exists(), f"Missing {p_preds}"
    assert p_results.exists(), f"Missing {p_results}"
    assert p_market_exp.exists(), f"Missing {p_market_exp}"

    df_preds = pd.read_parquet(p_preds)
    with open(p_results, "r", encoding="utf-8") as f:
        results_json = json.load(f)

    # 1. Prediction Metrics Reconciliation
    print("\n--- 1. PREDICTION METRICS AUDIT ---")
    y_true = df_preds["target_return"].values
    y_pred = df_preds["predicted_return"].values
    n_total = len(df_preds)

    rmse_zero = np.sqrt(np.mean(y_true ** 2))
    mae_zero = np.mean(np.abs(y_true))
    rmse_ridge = np.sqrt(np.mean((y_true - y_pred) ** 2))
    mae_ridge = np.mean(np.abs(y_true - y_pred))
    bias_ridge = np.mean(y_pred - y_true)
    hit_rate = np.mean(np.sign(y_true) == np.sign(y_pred))

    print(f"Total Rows: {n_total} (Claimed: {results_json['metadata']['total_out_of_sample_observations']})")
    assert n_total == results_json["metadata"]["total_out_of_sample_observations"]

    print(f"Zero RMSE: {rmse_zero:.6f} vs Saved: {results_json['aggregate_metrics']['reference_0_zero']['rmse']:.6f}")
    print(f"Ridge RMSE: {rmse_ridge:.6f} vs Saved: {results_json['aggregate_metrics']['ridge_cross_sectional']['rmse']:.6f}")
    print(f"Ridge MAE: {mae_ridge:.6f} vs Saved: {results_json['aggregate_metrics']['ridge_cross_sectional']['mae']:.6f}")
    print(f"Ridge Bias: {bias_ridge:+.6f} vs Saved: {results_json['aggregate_metrics']['ridge_cross_sectional']['bias']:+.6f}")
    print(f"Ridge Hit Rate: {hit_rate*100:.2f}% vs Saved: {results_json['aggregate_metrics']['ridge_cross_sectional']['hit_rate']*100:.2f}%")

    # 2. Rank IC & Statistical Inference Audit
    print("\n--- 2. RANK IC & STATISTICAL INFERENCE AUDIT ---")
    # A. Pooled Spearman Rank Correlation
    pooled_ic, pooled_pval = spearmanr(y_true, y_pred)
    print(f"Pooled Spearman Rank IC: {pooled_ic:+.4f} (Pooled unadjusted p-val: {pooled_pval:.2e})")

    # B. Daily Cross-Sectional Spearman Rank Correlation
    daily_ic_records = []
    dates = sorted(df_preds["trading_date"].unique().tolist())
    for d in dates:
        d_sub = df_preds[df_preds["trading_date"] == d]
        if len(d_sub) >= 10:
            c, _ = spearmanr(d_sub["target_return"], d_sub["predicted_return"])
            if not np.isnan(c):
                daily_ic_records.append((d, float(c), len(d_sub)))

    df_daily_ic = pd.DataFrame(daily_ic_records, columns=["trading_date", "ic", "n_stocks"])
    mean_daily_ic = float(df_daily_ic["ic"].mean())
    std_daily_ic = float(df_daily_ic["ic"].std(ddof=1))
    T_dates = len(df_daily_ic)
    ir_ic = mean_daily_ic / std_daily_ic if std_daily_ic > 0 else 0.0

    # Newey-West HAC adjusted standard error (L=4 for H=5 forward returns)
    ic_vals = df_daily_ic["ic"].values
    gamma_0 = float(np.var(ic_vals, ddof=1))
    L = 4
    gammas = []
    for l in range(1, L + 1):
        g_l = float(np.cov(ic_vals[:-l], ic_vals[l:])[0, 1])
        gammas.append(g_l)

    v_hac = gamma_0 + 2.0 * sum((1.0 - (l / (L + 1.0))) * gammas[l - 1] for l in range(1, L + 1))
    se_hac = float(np.sqrt(max(v_hac, 1e-12) / T_dates))
    t_hac = float(mean_daily_ic / se_hac) if se_hac > 0 else 0.0
    p_hac = float(2.0 * (1.0 - t.cdf(abs(t_hac), df=T_dates - 1)))

    # Block bootstrap (blocks of 5 contiguous trading sessions)
    n_bootstrap = 2000
    block_size = 5
    n_blocks = int(np.ceil(T_dates / block_size))
    boot_means = []
    np.random.seed(42)
    for _ in range(n_bootstrap):
        block_starts = np.random.randint(0, T_dates - block_size + 1, size=n_blocks)
        sample_indices = []
        for bs in block_starts:
            sample_indices.extend(range(bs, bs + block_size))
        sample_indices = sample_indices[:T_dates]
        boot_means.append(float(np.mean(ic_vals[sample_indices])))

    boot_ci_low = float(np.percentile(boot_means, 2.5))
    boot_ci_high = float(np.percentile(boot_means, 97.5))
    boot_pval = float(np.mean(np.array(boot_means) >= 0.0) * 2.0)
    if boot_pval > 1.0:
        boot_pval = float(np.mean(np.array(boot_means) <= 0.0) * 2.0)

    print(f"Total Unique Trading Dates: {T_dates}")
    print(f"Mean Daily Cross-Sectional IC : {mean_daily_ic:+.4f}")
    print(f"Daily Cross-Sectional IC Std  : {std_daily_ic:.4f}")
    print(f"Information Ratio of IC (IR)  : {ir_ic:+.4f}")
    print(f"Newey-West HAC (L=4) SE       : {se_hac:.4f}")
    print(f"Newey-West HAC t-statistic    : {t_hac:+.3f} (p-value = {p_hac:.4f})")
    print(f"5-Date Block Bootstrap 95% CI : [{boot_ci_low:+.4f}, {boot_ci_high:+.4f}] (p-value = {boot_pval:.4f})")

    # 3. Portfolio Simulation and Accounting Audit
    print("\n--- 3. PORTFOLIO SIMULATION & ACCOUNTING RECONCILIATION ---")
    cost_cfg = TransactionCostConfig(
        entry_fee_bps=2.5, exit_fee_bps=2.5, half_spread_bps=2.5, slippage_bps=2.5
    )
    risk_cfg = RiskGateConfig(
        buy_threshold=0.015,
        sell_threshold=-0.015,
        max_uncertainty=0.08,
        min_net_return_hurdle=0.005,
        enforce_uncertainty_gate=True,
    )

    decisions_audit = []
    for idx in range(len(df_preds)):
        row = df_preds.iloc[idx]
        u_est = ResidualUncertaintyEstimator(residual_std=float(row["sigma_train"]), method_name="sigma")
        policy = ThresholdDecisionPolicy(uncertainty_estimator=u_est)
        req = DecisionContractRequest(
            company_id=row["company_id"],
            ticker=row["ticker"],
            decision_timestamp=f"{row['trading_date']}T14:15:00Z",
            predicted_forward_return=float(row["predicted_return"]),
            forecast_uncertainty=float(row["sigma_train"]),
            rolling_volatility_5d=float(row["market_volatility_5d"]) if pd.notna(row["market_volatility_5d"]) else None,
            feature_metadata={"n_features_used": 17, "n_features_required": 17},
            model_id=f"Ridge_Fold{row['fold']}",
            training_cutoff_date="2020-03-23",
            cost_config=cost_cfg,
            risk_config=risk_cfg,
        )
        resp = policy.evaluate(req)
        decisions_audit.append({
            "trading_date": row["trading_date"],
            "ticker": row["ticker"],
            "company_id": row["company_id"],
            "signal": resp.signal.value,
            "expected_net_return": resp.expected_net_return,
        })

    df_decisions_audit = pd.DataFrame(decisions_audit)
    sig_counts = df_decisions_audit["signal"].value_counts().to_dict()
    print(f"Audit Decision Signals: {sig_counts}")

    port_cfg = PortfolioConfig(
        initial_cash=100000.0,
        max_concurrent_positions=10,
        max_position_weight=0.10,
        holding_horizon_sessions=5,
        cost_config=cost_cfg,
    )
    sim = DeterministicPortfolioSimulator(port_cfg)

    # Market slice for execution
    df_raw_mkt = pd.read_parquet(p_market_exp)
    sub_mkt = df_raw_mkt[
        (df_raw_mkt["trading_date"] >= "2019-09-17") & (df_raw_mkt["trading_date"] <= "2020-06-15")
    ].copy()
    adj_factor = sub_mkt["adjusted_close"] / sub_mkt["close"]
    sub_mkt["adjusted_open"] = sub_mkt["open"] * adj_factor

    sim_res = sim.simulate(df_decisions_audit, sub_mkt, "Phase5J_AuditSim")

    print(f"Sim Final Equity        : ${sim_res.final_equity:,.2f} vs Saved: ${results_json['portfolio_simulation']['cross_sectional_policy']['final_equity']:,.2f}")
    print(f"Sim Total Net Return    : {sim_res.total_net_return*100:+.2f}% vs Saved: {results_json['portfolio_simulation']['cross_sectional_policy']['total_net_return']*100:+.2f}%")
    print(f"Sim Max Drawdown        : {sim_res.max_drawdown*100:.2f}% vs Saved: {results_json['portfolio_simulation']['cross_sectional_policy']['max_drawdown']*100:.2f}%")
    print(f"Sim Closed Trades       : {sim_res.total_closed_trades} vs Saved: {results_json['portfolio_simulation']['cross_sectional_policy']['total_closed_trades']}")
    print(f"Sim Win Rate            : {sim_res.win_rate*100:.1f}% vs Saved: {results_json['portfolio_simulation']['cross_sectional_policy']['win_rate']*100:.1f}%")
    print(f"Sim Total Costs         : ${sim_res.total_transaction_costs:.2f} vs Saved: ${results_json['portfolio_simulation']['cross_sectional_policy']['total_transaction_costs']:.2f}")
    print(f"Sim Rejected Orders     : {sim_res.total_rejected_orders} vs Saved: {results_json['portfolio_simulation']['cross_sectional_policy']['total_rejected_orders']}")
    print(f"Rejection Reasons       : {sim_res.rejection_breakdown}")

    # Verify reconciliation of all 112 candidate signals
    n_buy = sig_counts.get("BUY", 0)
    n_closed = sim_res.total_closed_trades
    n_rejected = sim_res.total_rejected_orders
    n_reconciled = n_closed + n_rejected
    print(f"\nOrder Reconciliation Formula: BUY({n_buy}) = ClosedTrades({n_closed}) + RejectedOrders({n_rejected}) -> {n_reconciled} == {n_buy}: {n_reconciled == n_buy}")

    # Check terminal cash conservation on daily snapshots
    terminal_cash_check = True
    for s in sim_res.daily_history:
        calc_eq = s.cash + s.invested_capital
        if abs(calc_eq - s.portfolio_equity) > 0.01:
            terminal_cash_check = False
            print(f"Cash reconciliation anomaly on {s.date}: Cash={s.cash}, Invested={s.invested_capital}, Eq={s.portfolio_equity}")

    print(f"Daily Equity & Cash Accounting Conservation Checked: {'PASSED' if terminal_cash_check else 'FAILED'}")

    return {
        "n_total": n_total,
        "rmse_zero": rmse_zero,
        "rmse_ridge": rmse_ridge,
        "mae_zero": mae_zero,
        "mae_ridge": mae_ridge,
        "hit_rate": hit_rate,
        "pooled_ic": pooled_ic,
        "mean_daily_ic": mean_daily_ic,
        "std_daily_ic": std_daily_ic,
        "ir_ic": ir_ic,
        "se_hac": se_hac,
        "t_hac": t_hac,
        "p_hac": p_hac,
        "boot_ci": [boot_ci_low, boot_ci_high],
        "boot_pval": boot_pval,
        "final_equity": sim_res.final_equity,
        "total_net_return": sim_res.total_net_return,
        "max_drawdown": sim_res.max_drawdown,
        "total_closed_trades": sim_res.total_closed_trades,
        "win_rate": sim_res.win_rate,
        "total_rejected_orders": sim_res.total_rejected_orders,
        "rejection_breakdown": sim_res.rejection_breakdown,
    }


if __name__ == "__main__":
    audit_phase5j1()

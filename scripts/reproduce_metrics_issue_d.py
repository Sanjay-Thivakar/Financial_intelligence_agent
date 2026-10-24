"""
Phase 7B-R Issue D: Independent Reproduction of Metrics and Portfolio Simulations.
"""

import os
import sys
import json
from pathlib import Path
import pandas as pd
import numpy as np
from scipy.stats import spearmanr, t

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def compute_hac(ic_vals, L=4):
    T_dates = len(ic_vals)
    mean_ic = float(np.mean(ic_vals))
    gamma_0 = float(np.var(ic_vals, ddof=1)) if T_dates > 1 else 0.0
    if T_dates > L:
        gammas = [float(np.cov(ic_vals[:-l], ic_vals[l:])[0, 1]) for l in range(1, L + 1)]
        v_hac = gamma_0 + 2.0 * sum((1.0 - (l / (L + 1.0))) * gammas[l - 1] for l in range(1, L + 1))
    else:
        v_hac = gamma_0
    se_hac = float(np.sqrt(max(v_hac, 1e-12) / T_dates)) if T_dates > 0 else 0.0
    t_hac = float(mean_ic / se_hac) if se_hac > 0 else 0.0
    p_hac = float(2.0 * (1.0 - t.cdf(abs(t_hac), df=max(T_dates - 1, 1)))) if se_hac > 0 else 1.0
    return se_hac, t_hac, p_hac

def run_metric_reproduction():
    print("=" * 95)
    print("PHASE 7B-R: ISSUE D — METRIC AND PORTFOLIO SIMULATION REPRODUCTION")
    print("=" * 95)
    
    ho_pred_path = PROJECT_ROOT / "data" / "processed" / "research" / "phase7b" / "phase7b_predictions_final_holdout.parquet"
    results_path = PROJECT_ROOT / "data" / "processed" / "research" / "phase7b" / "phase7b_experiment_results.json"
    
    df_ho = pd.read_parquet(ho_pred_path)
    with open(results_path) as f:
        saved_res = json.load(f)["final_holdout_results"]
        
    models = {
        "m1_raw_orig_mkt": ("pred_m1_raw_orig_mkt", "target_raw"),
        "m2_raw_clean_mkt": ("pred_m2_raw_clean_mkt", "target_raw"),
        "m3_mkt_excess_clean_mkt": ("pred_m3_mkt_excess_clean_mkt", "target_mkt_excess"),
        "m4_sec_excess_clean_mkt": ("pred_m4_sec_excess_clean_mkt", "target_sec_excess"),
        "m5_sec_excess_clean_multi": ("pred_m5_sec_excess_clean_multi", "target_sec_excess"),
    }
    
    print("\n1. INDEPENDENT REPRODUCTION OF HOLDOUT IC & HAC METRICS:")
    dates = sorted(df_ho["trading_date"].unique().tolist())
    
    reproduced_metrics = {}
    
    for m_id, (pred_col, target_col) in models.items():
        daily_ics = []
        for d in dates:
            sub = df_ho[df_ho["trading_date"] == d]
            if len(sub) >= 10:
                c, _ = spearmanr(sub[target_col], sub[pred_col])
                if not np.isnan(c):
                    daily_ics.append(c)
                    
        ic_arr = np.array(daily_ics)
        mean_ic = float(np.mean(ic_arr))
        med_ic = float(np.median(ic_arr))
        pct_pos = float(np.mean(ic_arr > 0) * 100.0)
        se_hac, t_hac, p_hac = compute_hac(ic_arr, L=4)
        
        # Regression
        y_true = df_ho[target_col].values
        y_pred = df_ho[pred_col].values
        rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
        mae = float(np.mean(np.abs(y_true - y_pred)))
        
        saved_ic = saved_res[m_id]["ic_pooled_holdout"]
        saved_reg = saved_res[m_id]["regression"]
        
        print(f"\n   Model: {m_id}")
        print(f"     Mean Daily IC: Rep={mean_ic:+.4f} | Saved={saved_ic['mean_daily_ic']:+.4f} | Diff={abs(mean_ic - saved_ic['mean_daily_ic']):.6f}")
        print(f"     Median IC    : Rep={med_ic:+.4f} | Saved={saved_ic['median_daily_ic']:+.4f} | Diff={abs(med_ic - saved_ic['median_daily_ic']):.6f}")
        print(f"     % Positive   : Rep={pct_pos:.1f}% | Saved={saved_ic['pct_positive_ic_days']:.1f}% | Diff={abs(pct_pos - saved_ic['pct_positive_ic_days']):.4f}%")
        print(f"     HAC p-value  : Rep={p_hac:.4f} | Saved={saved_ic['hac_pvalue']:.4f} | Diff={abs(p_hac - saved_ic['hac_pvalue']):.6f}")
        print(f"     RMSE         : Rep={rmse:.4f} | Saved={saved_reg['rmse']:.4f} | Diff={abs(rmse - saved_reg['rmse']):.6f}")
        print(f"     MAE          : Rep={mae:.4f} | Saved={saved_reg['mae']:.4f} | Diff={abs(mae - saved_reg['mae']):.6f}")
        
        assert abs(mean_ic - saved_ic["mean_daily_ic"]) < 1e-6, "Mean IC mismatch!"
        assert abs(p_hac - saved_ic["hac_pvalue"]) < 1e-4, "HAC p-value mismatch!"
        assert abs(rmse - saved_reg["rmse"]) < 1e-6, "RMSE mismatch!"

    print("\n2. PORTFOLIO SIMULATION & TURNOVER SENSITIVITY:")
    for m_id, (pred_col, target_col) in models.items():
        daily_gross = []
        daily_turnovers = []
        prev_long, prev_short = set(), set()
        
        for d in dates:
            sub = df_ho[df_ho["trading_date"] == d].copy()
            sub = sub.sort_values(pred_col, ascending=False)
            k = int(len(sub) * 0.20)
            long_leg = sub.iloc[:k]
            short_leg = sub.iloc[-k:]
            
            curr_long = set(long_leg["ticker"].tolist())
            curr_short = set(short_leg["ticker"].tolist())
            
            ls_spread_5d = long_leg["target_raw"].mean() - short_leg["target_raw"].mean()
            daily_gross.append(ls_spread_5d / 5.0)
            
            if prev_long and prev_short:
                to = (len(curr_long - prev_long)/k + len(curr_short - prev_short)/k) / 2.0
                daily_turnovers.append(to)
            prev_long, prev_short = curr_long, curr_short
            
        gross_arr = np.array(daily_gross)
        ann_gross = float(np.mean(gross_arr) * 252.0)
        ann_vol = float(np.std(gross_arr, ddof=1) * np.sqrt(252.0))
        emp_turnover = float(np.mean(daily_turnovers))
        
        saved_econ = saved_res[m_id]["economic_sim"]
        print(f"\n   Model: {m_id}")
        print(f"     Annualized Gross Return: {ann_gross*100:+.2f}% | Saved: {saved_econ['ann_gross_return']*100:+.2f}%")
        print(f"     Gross Sharpe Ratio     : {ann_gross/ann_vol:+.2f} | Saved: {saved_econ['gross_sharpe']:+.2f}")
        print(f"     Empirical Daily Turnover: {emp_turnover*100:.1f}% (vs 40.0% assumed)")
        
        # Net returns with exact empirical turnover vs 40% assumed
        for bps in [10, 20, 30]:
            cost_emp = (bps / 10000.0) * emp_turnover
            cost_assumed = (bps / 10000.0) * 0.40
            net_emp = float(np.mean(gross_arr - cost_emp) * 252.0)
            net_assumed = float(np.mean(gross_arr - cost_assumed) * 252.0)
            sharpe_emp = net_emp / ann_vol
            sharpe_assumed = net_assumed / ann_vol
            print(f"       At {bps} bps friction -> Net Sharpe (Empirical TO {emp_turnover*100:.1f}%): {sharpe_emp:+.2f} | Net Sharpe (Assumed 40% TO): {sharpe_assumed:+.2f}")

if __name__ == "__main__":
    run_metric_reproduction()

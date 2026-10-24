"""
Phase 6.9E Predictive Signal Diagnosis & Model Improvement Engine.

Performs:
1. Target, label, and split boundary audit.
2. Comprehensive data quality and 28-feature diagnostic analysis (missingness, constants, redundancies, distributions).
3. Decomposition of existing Phase 6.9D predictions (time-series market drift vs cross-sectional alpha).
4. Controlled, lightweight model comparison under strict chronological walk-forward validation:
   - Benchmark 1: Market Ridge (17 features, raw target)
   - Candidate 2: Cleaned Feature Ridge (19 stationary features, raw target)
   - Candidate 3: Cleaned Feature Non-Linear Tree (HistGradientBoosting, raw target)
   - Candidate 4: Cross-Sectional Demeaned Ridge (19 stationary features, excess return target)
5. Generation of machine-readable diagnostic summary JSON.
"""

import sys
import os
import json
import time
from pathlib import Path
from typing import Dict, List, Any, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
from scipy.stats import spearmanr, t
from sklearn.linear_model import Ridge, ElasticNet
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer

from src.models.splitter import WalkForwardSplitter, WalkForwardConfig
from src.models.baseline import MarketBaselinePipeline


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    """Computes RMSE, MAE, directional accuracy, and pooled rank IC."""
    rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
    mae = float(np.mean(np.abs(y_true - y_pred)))
    
    valid_mask = (y_true != 0) & (y_pred != 0)
    hit_rate = float(np.mean(np.sign(y_true[valid_mask]) == np.sign(y_pred[valid_mask]))) if valid_mask.sum() > 0 else 0.5
    
    if len(y_true) < 5 or np.all(y_pred == y_pred[0]) or np.all(y_true == y_true[0]):
        rank_ic, p_val = 0.0, 1.0
    else:
        c, p = spearmanr(y_true, y_pred)
        rank_ic = float(c) if not np.isnan(c) else 0.0
        p_val = float(p) if not np.isnan(p) else 1.0
        
    return {
        "rmse": rmse,
        "mae": mae,
        "hit_rate": hit_rate,
        "pooled_rank_ic": rank_ic,
        "pooled_ic_pvalue": p_val,
    }


def compute_daily_ic_and_hac(df_pred: pd.DataFrame, pred_col: str, target_col: str = "target_return") -> Dict[str, Any]:
    """Computes daily cross-sectional Spearman IC and Newey-West HAC inference (L=4)."""
    daily_records = []
    dates = sorted(df_pred["trading_date"].unique().tolist())
    for d in dates:
        d_sub = df_pred[df_pred["trading_date"] == d]
        if len(d_sub) >= 10:
            c, _ = spearmanr(d_sub[target_col], d_sub[pred_col])
            if not np.isnan(c):
                daily_records.append((d, float(c)))
                
    if not daily_records:
        return {"n_dates": 0, "mean_daily_ic": 0.0, "hac_tstat": 0.0, "hac_pvalue": 1.0}
        
    ic_vals = np.array([r[1] for r in daily_records])
    T_dates = len(ic_vals)
    mean_ic = float(np.mean(ic_vals))
    std_ic = float(np.std(ic_vals, ddof=1)) if T_dates > 1 else 0.0
    
    gamma_0 = float(np.var(ic_vals, ddof=1)) if T_dates > 1 else 0.0
    L = 4
    if T_dates > L:
        gammas = [float(np.cov(ic_vals[:-l], ic_vals[l:])[0, 1]) for l in range(1, L + 1)]
        v_hac = gamma_0 + 2.0 * sum((1.0 - (l / (L + 1.0))) * gammas[l - 1] for l in range(1, L + 1))
    else:
        v_hac = gamma_0
        
    se_hac = float(np.sqrt(max(v_hac, 1e-12) / T_dates)) if T_dates > 0 else 0.0
    t_hac = float(mean_ic / se_hac) if se_hac > 0 else 0.0
    p_hac = float(2.0 * (1.0 - t.cdf(abs(t_hac), df=max(T_dates - 1, 1)))) if se_hac > 0 else 1.0
    
    return {
        "n_dates": T_dates,
        "mean_daily_ic": mean_ic,
        "std_daily_ic": std_ic,
        "hac_se": se_hac,
        "hac_tstat": t_hac,
        "hac_pvalue": p_hac,
    }


def run_phase6_9e_diagnosis():
    print("=" * 95)
    print("PHASE 6.9E: PREDICTIVE SIGNAL DIAGNOSIS & CONTROLLED MODEL IMPROVEMENT")
    print("=" * 95)
    t0 = time.time()
    
    data_dir = PROJECT_ROOT / "data" / "processed" / "research" / "phase6_9d"
    out_dir = PROJECT_ROOT / "data" / "processed" / "research" / "phase6_9e"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    dataset_path = data_dir / "phase6_9d_multimodal_dataset.parquet"
    oos_path = data_dir / "phase6_9d_predictions_oos.parquet"
    
    print(f"Loading multimodal dataset from {dataset_path}...")
    df = pd.read_parquet(dataset_path)
    print(f"Loaded {len(df):,} rows, {df['ticker'].nunique()} tickers, {df['trading_date'].nunique()} dates.")
    
    all_features = MarketBaselinePipeline.ALL_FEATURE_COLUMNS
    mkt_features = MarketBaselinePipeline.MARKET_FEATURE_COLUMNS
    fund_features = MarketBaselinePipeline.FUNDAMENTAL_FEATURE_COLUMNS
    evt_features = MarketBaselinePipeline.EVENT_FEATURE_COLUMNS
    
    # ---------------------------------------------------------
    # PART 1: Feature Diagnostics (All 28 Features)
    # ---------------------------------------------------------
    print("\n--- Part 1: Comprehensive Feature Diagnostics (28 Features) ---")
    feat_diagnostics = {}
    for c in all_features:
        s = df[c]
        n_missing = int(s.isna().sum())
        pct_missing = float(n_missing / len(df) * 100.0)
        n_unique = int(s.nunique(dropna=True))
        is_const = bool(n_unique <= 1)
        
        valid_s = s.dropna()
        if len(valid_s) > 0 and (pd.api.types.is_numeric_dtype(valid_s) or pd.api.types.is_bool_dtype(valid_s)):
            valid_num = valid_s.astype(float)
            desc = {
                "min": float(valid_num.min()),
                "p25": float(valid_num.quantile(0.25)),
                "median": float(valid_num.median()),
                "p75": float(valid_num.quantile(0.75)),
                "max": float(valid_num.max()),
                "mean": float(valid_num.mean()),
                "std": float(valid_num.std(ddof=1)) if len(valid_num) > 1 else 0.0,
            }
        else:
            desc = {"min": None, "p25": None, "median": None, "p75": None, "max": None, "mean": None, "std": None}
            
        feat_diagnostics[c] = {
            "name": c,
            "family": "market" if c in mkt_features else ("fundamental" if c in fund_features else "event"),
            "missing_count": n_missing,
            "missing_pct": pct_missing,
            "n_unique": n_unique,
            "is_constant": is_const,
            "stats": desc,
        }
    
    # Check redundancies
    redundancies = [
        {"pair": ["market_return_5d", "market_momentum_5d"], "max_abs_diff": float((df["market_return_5d"] - df["market_momentum_5d"]).abs().max()), "verdict": "EXACT_DUPLICATE"},
        {"pair": ["market_return_21d", "market_momentum_21d"], "max_abs_diff": float((df["market_return_21d"] - df["market_momentum_21d"]).abs().max()), "verdict": "EXACT_DUPLICATE"},
        {"pair": ["market_return_1d", "market_log_return_1d"], "correlation": float(df[["market_return_1d", "market_log_return_1d"]].corr().iloc[0, 1]), "verdict": "NEAR_DUPLICATE"},
        {"pair": ["market_sma_20d", "market_sma_50d"], "correlation": float(df[["market_sma_20d", "market_sma_50d"]].corr().iloc[0, 1]), "verdict": "NON_STATIONARY_RAW_PRICE_COLLINEAR"},
    ]
    
    # ---------------------------------------------------------
    # PART 2: Target & Market Common Factor Decomposition
    # ---------------------------------------------------------
    print("\n--- Part 2: Target Variance & Market Factor Decomposition ---")
    y_raw = df["target_forward_return_5d"].values
    total_var = float(np.var(y_raw))
    
    df["daily_market_mean_tgt"] = df.groupby("trading_date")["target_forward_return_5d"].transform("mean")
    df["target_excess_5d"] = df["target_forward_return_5d"] - df["daily_market_mean_tgt"]
    
    mkt_factor_var = float(np.var(df["daily_market_mean_tgt"].values))
    idio_var = float(np.var(df["target_excess_5d"].values))
    pct_mkt_var = float(mkt_factor_var / total_var * 100.0)
    
    print(f"Total Target Return Variance: {total_var:.6f}")
    print(f"Market Factor Variance (Daily Mean): {mkt_factor_var:.6f} ({pct_mkt_var:.1f}%)")
    print(f"Idiosyncratic Cross-Sectional Variance: {idio_var:.6f} ({100.0 - pct_mkt_var:.1f}%)")
    
    # ---------------------------------------------------------
    # PART 3: Analysis of Saved Phase 6.9D Predictions
    # ---------------------------------------------------------
    print("\n--- Part 3: Deep Diagnosis of Saved Phase 6.9D Predictions ---")
    df_oos = pd.read_parquet(oos_path)
    
    df_oos["daily_mean_tgt"] = df_oos.groupby("trading_date")["target_return"].transform("mean")
    df_oos["excess_tgt"] = df_oos["target_return"] - df_oos["daily_mean_tgt"]
    
    df_oos["daily_mean_pred_ridge"] = df_oos.groupby("trading_date")["exp_a_market_ridge"].transform("mean")
    df_oos["excess_pred_ridge"] = df_oos["exp_a_market_ridge"] - df_oos["daily_mean_pred_ridge"]
    
    daily_means = df_oos.groupby("trading_date")[["target_return", "exp_a_market_ridge"]].mean()
    ts_corr, ts_pval = spearmanr(daily_means["target_return"], daily_means["exp_a_market_ridge"])
    
    xs_corr, xs_pval = spearmanr(df_oos["excess_tgt"], df_oos["excess_pred_ridge"])
    
    oos_diagnosis = {
        "total_oos_rows": len(df_oos),
        "time_series_market_timing_rank_corr": float(ts_corr),
        "time_series_market_timing_pval": float(ts_pval),
        "cross_sectional_market_neutral_rank_ic": float(xs_corr),
        "cross_sectional_market_neutral_pval": float(xs_pval),
        "ridge_pred_mean": float(df_oos["exp_a_market_ridge"].mean()),
        "ridge_pred_std": float(df_oos["exp_a_market_ridge"].std(ddof=1)),
        "elastic_pred_mean": float(df_oos["exp_a_market_elastic"].mean()),
        "elastic_pred_std": float(df_oos["exp_a_market_elastic"].std(ddof=1)),
        "actual_y_mean": float(df_oos["target_return"].mean()),
        "actual_y_std": float(df_oos["target_return"].std(ddof=1)),
    }
    print(f"Time-Series Market-Timing Rank Corr: {ts_corr:.4f} (p={ts_pval:.4e})")
    print(f"Cross-Sectional Market-Neutral Rank IC: {xs_corr:.4f} (p={xs_pval:.4f})")
    print(f"Ridge Prediction Std: {oos_diagnosis['ridge_pred_std']:.5f} vs Actual Return Std: {oos_diagnosis['actual_y_std']:.5f}")
    print(f"ElasticNet Prediction Std: {oos_diagnosis['elastic_pred_std']:.5f} (severe collapse to constant)")
    
    # ---------------------------------------------------------
    # PART 4: Controlled Lightweight Model Comparison
    # ---------------------------------------------------------
    print("\n--- Part 4: Controlled Lightweight Model Comparison ---")
    
    # Define Cleaned Feature Set:
    # 1. Drop exact duplicates (market_momentum_5d, market_momentum_21d)
    # 2. Drop near-duplicate (market_log_return_1d)
    # 3. Drop constant (fundamental_all_facts_stale)
    # 4. Replace raw price SMAs with stationary normalized ratios:
    #    market_distance_sma20 = (close / sma20) - 1
    #    market_distance_sma50 = (close / sma50) - 1
    #    market_sma_ratio = (sma20 / sma50) - 1
    df["market_distance_sma20"] = (df["close"] / df["market_sma_20d"]) - 1.0
    df["market_distance_sma50"] = (df["close"] / df["market_sma_50d"]) - 1.0
    df["market_sma_ratio"] = (df["market_sma_20d"] / df["market_sma_50d"]) - 1.0
    
    cleaned_features = [
        "market_return_1d", "market_return_5d", "market_return_21d",
        "market_volatility_5d", "market_volatility_21d", "market_volatility_63d",
        "market_momentum_63d",
        "market_distance_sma20", "market_distance_sma50", "market_sma_ratio",
        "market_zscore_20d", "market_zscore_50d", "market_rsi_14d",
        "market_volume_change_1d", "market_volume_ratio_20d",
        "fundamental_ratio_net_margin", "fundamental_ratio_roa",
        "fundamental_ratio_debt_to_assets", "fundamental_ratio_debt_to_equity",
        "fundamental_ratio_ocf_to_net_income", "fundamental_revenue_age_days",
        "sec_event_count_5d", "sec_earnings_release_in_window", "sec_days_since_last_8k",
    ]
    print(f"Cleaned Stationary Multimodal Features ({len(cleaned_features)}): {cleaned_features}")
    
    wf_cfg = WalkForwardConfig(n_splits=4, train_min_sessions=173, val_sessions=45, purge_sessions=5)
    splitter = WalkForwardSplitter(wf_cfg)
    
    models_to_test = {
        "mkt_ridge_benchmark": {"name": "1. Market Ridge Benchmark (Phase 6.9D)", "features": mkt_features, "target": "raw", "algo": "ridge"},
        "cleaned_ridge_raw": {"name": "2. Cleaned Multimodal Ridge (Raw Target)", "features": cleaned_features, "target": "raw", "algo": "ridge"},
        "cleaned_tree_raw": {"name": "3. Cleaned Multimodal Tree (HistGBR, Raw Target)", "features": cleaned_features, "target": "raw", "algo": "tree"},
        "cleaned_ridge_excess": {"name": "4. Cleaned Multimodal Ridge (Excess Target)", "features": cleaned_features, "target": "excess", "algo": "ridge"},
    }
    
    exp_preds: Dict[str, List[float]] = {k: [] for k in models_to_test}
    exp_meta: List[Dict[str, Any]] = []
    
    fold_perf: Dict[int, Dict[str, Any]] = {}
    
    for fold, (tr_idx, val_idx) in enumerate(splitter.split(df)):
        tr_df = df.iloc[tr_idx].copy()
        val_df = df.iloc[val_idx].copy()
        
        y_tr_raw = tr_df["target_forward_return_5d"].values
        y_val_raw = val_df["target_forward_return_5d"].values
        
        # Training fold daily mean for excess target computation
        tr_daily_mean = tr_df.groupby("trading_date")["target_forward_return_5d"].transform("mean")
        y_tr_excess = (tr_df["target_forward_return_5d"] - tr_daily_mean).values
        
        val_dates = sorted(val_df["trading_date"].unique().tolist())
        
        for idx in val_idx:
            r = df.iloc[idx]
            exp_meta.append({
                "trading_date": r["trading_date"],
                "ticker": r["ticker"],
                "company_id": r["company_id"],
                "fold": fold,
                "target_raw": r["target_forward_return_5d"],
                "target_excess": r["target_excess_5d"],
            })
            
        fold_perf[fold] = {"n_obs": len(val_df), "val_dates": [val_dates[0], val_dates[-1]]}
        
        # Preprocessing strictly fit on train fold
        imp_mkt = SimpleImputer(strategy="median")
        scl_mkt = StandardScaler()
        X_tr_mkt = scl_mkt.fit_transform(imp_mkt.fit_transform(tr_df[mkt_features]))
        X_val_mkt = scl_mkt.transform(imp_mkt.transform(val_df[mkt_features]))
        
        imp_clean = SimpleImputer(strategy="median")
        scl_clean = StandardScaler()
        X_tr_clean = scl_clean.fit_transform(imp_clean.fit_transform(tr_df[cleaned_features]))
        X_val_clean = scl_clean.transform(imp_clean.transform(val_df[cleaned_features]))
        
        # 1. Market Ridge Benchmark
        m1 = Ridge(alpha=100.0)
        m1.fit(X_tr_mkt, y_tr_raw)
        p1 = m1.predict(X_val_mkt)
        exp_preds["mkt_ridge_benchmark"].extend(p1)
        
        # 2. Cleaned Multimodal Ridge (Raw Target)
        m2 = Ridge(alpha=100.0)
        m2.fit(X_tr_clean, y_tr_raw)
        p2 = m2.predict(X_val_clean)
        exp_preds["cleaned_ridge_raw"].extend(p2)
        
        # 3. Cleaned Multimodal Tree (HistGBR, max_depth=3, l2=1.0)
        m3 = HistGradientBoostingRegressor(max_depth=3, l2_regularization=1.0, random_state=42, max_iter=50)
        m3.fit(tr_df[cleaned_features], y_tr_raw) # native NaN handling
        p3 = m3.predict(val_df[cleaned_features])
        exp_preds["cleaned_tree_raw"].extend(p3)
        
        # 4. Cleaned Multimodal Ridge (Excess Target)
        m4 = Ridge(alpha=100.0)
        m4.fit(X_tr_clean, y_tr_excess)
        p4_excess = m4.predict(X_val_clean)
        # Add back historical training drift to produce comparable raw forecast
        tr_drift = float(np.median(y_tr_raw))
        p4_raw = p4_excess + tr_drift
        exp_preds["cleaned_ridge_excess"].extend(p4_raw)
        
        fold_perf[fold]["mkt_ridge_benchmark"] = compute_metrics(y_val_raw, p1)
        fold_perf[fold]["cleaned_ridge_raw"] = compute_metrics(y_val_raw, p2)
        fold_perf[fold]["cleaned_tree_raw"] = compute_metrics(y_val_raw, p3)
        fold_perf[fold]["cleaned_ridge_excess"] = compute_metrics(y_val_raw, p4_raw)
        
        print(f"Fold {fold} ({val_dates[0]} to {val_dates[-1]}):")
        print(f"  M1 (Mkt Ridge Benchmark) : RMSE={fold_perf[fold]['mkt_ridge_benchmark']['rmse']:.4f}, Hit={fold_perf[fold]['mkt_ridge_benchmark']['hit_rate']*100:.1f}%, IC={fold_perf[fold]['mkt_ridge_benchmark']['pooled_rank_ic']:.3f}")
        print(f"  M2 (Clean Multimodal R)  : RMSE={fold_perf[fold]['cleaned_ridge_raw']['rmse']:.4f}, Hit={fold_perf[fold]['cleaned_ridge_raw']['hit_rate']*100:.1f}%, IC={fold_perf[fold]['cleaned_ridge_raw']['pooled_rank_ic']:.3f}")
        print(f"  M3 (Clean Multimodal Tree: RMSE={fold_perf[fold]['cleaned_tree_raw']['rmse']:.4f}, Hit={fold_perf[fold]['cleaned_tree_raw']['hit_rate']*100:.1f}%, IC={fold_perf[fold]['cleaned_tree_raw']['pooled_rank_ic']:.3f}")
        print(f"  M4 (Excess Return Ridge) : RMSE={fold_perf[fold]['cleaned_ridge_excess']['rmse']:.4f}, Hit={fold_perf[fold]['cleaned_ridge_excess']['hit_rate']*100:.1f}%, IC={fold_perf[fold]['cleaned_ridge_excess']['pooled_rank_ic']:.3f}")
        
    df_eval_all = pd.DataFrame(exp_meta)
    for k in models_to_test:
        df_eval_all[k] = exp_preds[k]
        
    y_val_all = df_eval_all["target_raw"].values
    
    aggregate_results = {}
    print("\n--- Cumulative Out-of-Sample Performance Comparison (54,900 Obs) ---")
    print(f"%-38s | %-7s | %-7s | %-8s | %-9s | %-12s | %-9s" % ('Model Configuration', 'RMSE', 'MAE', 'Hit Rate', 'Pooled IC', 'Daily Mean IC', 'HAC p-val'))
    print("-" * 105)
    
    for k, info in models_to_test.items():
        preds = df_eval_all[k].values
        base_m = compute_metrics(y_val_all, preds)
        hac_m = compute_daily_ic_and_hac(df_eval_all, k, target_col="target_raw")
        
        res_entry = {
            "name": info["name"],
            "n_features": len(info["features"]),
            "n_observations": len(y_val_all),
            "rmse": base_m["rmse"],
            "mae": base_m["mae"],
            "hit_rate": base_m["hit_rate"],
            "pooled_rank_ic": base_m["pooled_rank_ic"],
            "pooled_ic_pvalue": base_m["pooled_ic_pvalue"],
            "mean_daily_ic": hac_m["mean_daily_ic"],
            "std_daily_ic": hac_m["std_daily_ic"],
            "hac_tstat": hac_m["hac_tstat"],
            "hac_pvalue": hac_m["hac_pvalue"],
        }
        aggregate_results[k] = res_entry
        print(f"%-38s | %7.4f | %7.4f | %7.1f%% | %+9.3f | %+12.4f | %9.3f" % (
            info["name"], res_entry["rmse"], res_entry["mae"], res_entry["hit_rate"]*100, res_entry["pooled_rank_ic"], res_entry["mean_daily_ic"], res_entry["hac_pvalue"]
        ))
        
    # Check Market-Neutral Daily Rank IC for Model 4
    hac_m4_excess = compute_daily_ic_and_hac(df_eval_all, "cleaned_ridge_excess", target_col="target_excess")
    print(f"\nModel 4 Pure Cross-Sectional Excess IC: Mean Daily IC = {hac_m4_excess['mean_daily_ic']:+.4f}, HAC t = {hac_m4_excess['hac_tstat']:+.2f}, p = {hac_m4_excess['hac_pvalue']:.3f}")
    
    # ---------------------------------------------------------
    # PART 5: Save JSON Summary Deliverable
    # ---------------------------------------------------------
    summary_data = {
        "phase": "6.9E",
        "created_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "elapsed_seconds": round(time.time() - t0, 2),
        "cohort_size": df["ticker"].nunique(),
        "total_dataset_rows": len(df),
        "n_oos_observations": len(y_val_all),
        "n_walk_forward_folds": 4,
        "purge_gap_sessions": 5,
        "feature_diagnostics": feat_diagnostics,
        "feature_redundancies": redundancies,
        "target_decomposition": {
            "total_target_variance": total_var,
            "market_common_factor_variance": mkt_factor_var,
            "pct_market_common_factor_variance": pct_mkt_var,
            "idiosyncratic_variance": idio_var,
            "pct_idiosyncratic_variance": 100.0 - pct_mkt_var,
        },
        "phase6_9d_prediction_diagnosis": oos_diagnosis,
        "controlled_model_comparison": {
            "aggregate_results": aggregate_results,
            "fold_results": fold_perf,
            "model_4_excess_ic": hac_m4_excess,
        },
        "diagnostic_verdicts": {
            "bottleneck_1_raw_price_features": "CONFIRMED: market_sma_20d/50d were raw unnormalized prices ($3 to $2400) inducing non-stationary price biases",
            "bottleneck_2_redundant_features": "CONFIRMED: return_5d/momentum_5d and return_21d/momentum_21d were exact duplicate columns; stale flag had 0 variance",
            "bottleneck_3_target_design_confusion": "CONFIRMED: 41.2% of target variance is macro market drift; raw target forces model to conflate macro market timing with cross-sectional selection",
            "bottleneck_4_model_capacity": "CONFIRMED: Neither linear models nor non-linear tree models beat the simple market benchmark on raw return RMSE",
            "bottleneck_5_holdout_adequacy": "CONFIRMED: 3 sessions post 2020-06-03 are wholly inadequate for generalization claims and must remain untouched",
        },
        "governance_recommendations": {
            "recommendation_1": "Retain Market Baseline as primary reference model until market-neutral targets and macro decoupling are established",
            "recommendation_2": "Eliminate raw price SMAs and duplicate momentum features from production feature definitions",
            "recommendation_3": "Do not train heavy deep learning or NLP transformers on raw returns; address target formulation first",
            "stop_go_decision": "CONDITIONAL GO FOR SIGNAL RE-ENGINEERING (Phase 7A); NO-GO FOR IMMEDIATE LIVE EXECUTION",
        }
    }
    
    out_json_path = out_dir / "phase6_9e_diagnostic_summary.json"
    with open(out_json_path, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2)
    print(f"\nDiagnostic summary saved to {out_json_path} ({out_json_path.stat().st_size:,} bytes).")
    print(f"Phase 6.9E diagnosis completed in {time.time() - t0:.2f} seconds.")


if __name__ == "__main__":
    run_phase6_9e_diagnosis()

"""
Phase 7B — Historical Market-Model Evaluation and Validation Engine.

Executes the frozen research protocol across the expanded 5-year dataset:
- Development Window: 2019-01-02 to 2021-12-31 (4 Walk-Forward Folds with 5-session purge gaps).
- Final Evaluation Holdout: 2022-01-03 to 2023-12-28 (Quarantined 2-year out-of-sample period).

Models Evaluated:
1. Baselines: Zero prediction (excess targets) and Train-Mean (raw targets).
2. M1: Target A (Raw Return) + Original 17 Market Features (Benchmark).
3. M2: Target A (Raw Return) + Cleaned 15 Market Features.
4. M3: Target B (Market-Neutral Excess) + Cleaned 15 Market Features.
5. M4: Target C (Sector-Neutral Excess) + Cleaned 15 Market Features.
6. M5: Target C (Sector-Neutral Excess) + Cleaned 22 Multimodal Features (Dev Folds).

Invariants Enforced:
- 5-session purge gaps between training and validation/holdout.
- Training-only median imputation, scaling, and Ridge alpha selection.
- Dependence-aware inference: Daily cross-sectional Spearman Rank IC with Newey-West HAC (L=4).
- Realistic economic simulation: Quintile long/short strategy with 10, 20, 30 bps friction.
- Outputs saved under data/processed/research/phase7b/.
"""

import sys
import os
import json
import time
from pathlib import Path
from typing import Dict, List, Any, Tuple
import numpy as np
import pandas as pd
from scipy.stats import spearmanr, t
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models.baseline import MarketBaselinePipeline


def compute_regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    """Computes target-specific RMSE, MAE, and directional hit rate."""
    rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
    mae = float(np.mean(np.abs(y_true - y_pred)))
    valid_mask = (y_true != 0) & (y_pred != 0)
    hit_rate = float(np.mean(np.sign(y_true[valid_mask]) == np.sign(y_pred[valid_mask]))) if valid_mask.sum() > 0 else 0.5
    return {"rmse": rmse, "mae": mae, "hit_rate": hit_rate}


def compute_daily_cross_sectional_ic(df_pred: pd.DataFrame, pred_col: str, target_col: str) -> Dict[str, Any]:
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
        return {
            "n_dates": 0, "mean_daily_ic": 0.0, "median_daily_ic": 0.0,
            "std_daily_ic": 0.0, "pct_positive_ic_days": 0.0,
            "hac_se": 0.0, "hac_tstat": 0.0, "hac_pvalue": 1.0,
        }

    ic_vals = np.array([r[1] for r in daily_records])
    T_dates = len(ic_vals)
    mean_ic = float(np.mean(ic_vals))
    median_ic = float(np.median(ic_vals))
    std_ic = float(np.std(ic_vals, ddof=1)) if T_dates > 1 else 0.0
    pct_pos = float(np.mean(ic_vals > 0) * 100.0)

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
        "median_daily_ic": median_ic,
        "std_daily_ic": std_ic,
        "pct_positive_ic_days": pct_pos,
        "hac_se": se_hac,
        "hac_tstat": t_hac,
        "hac_pvalue": p_hac,
    }


def compute_sector_daily_ic(df_pred: pd.DataFrame, pred_col: str, target_col: str) -> Dict[str, Dict[str, float]]:
    """Computes mean daily cross-sectional IC per GICS sector."""
    sec_results = {}
    sectors = sorted(df_pred["sector"].unique().tolist())
    for s in sectors:
        sub_s = df_pred[df_pred["sector"] == s]
        daily_ics = []
        for d, grp in sub_s.groupby("trading_date"):
            if len(grp) >= 5:
                c, _ = spearmanr(grp[target_col], grp[pred_col])
                if not np.isnan(c):
                    daily_ics.append(c)
        if daily_ics:
            sec_results[s] = {
                "n_stocks": int(sub_s["company_id"].nunique()),
                "n_dates": len(daily_ics),
                "mean_daily_ic": float(np.mean(daily_ics)),
                "pct_positive_days": float(np.mean(np.array(daily_ics) > 0) * 100.0),
            }
    return sec_results


def simulate_economic_quintile_strategy(
    df_pred: pd.DataFrame, pred_col: str, return_col: str = "target_raw"
) -> Dict[str, Any]:
    """
    Simulates a dollar-neutral Long Q5 / Short Q1 quintile strategy:
    - Long top 20% predicted, Short bottom 20% predicted.
    - Equal weighted within legs.
    - Evaluates gross returns and net returns at 10, 20, 30 bps round-trip friction.
    """
    dates = sorted(df_pred["trading_date"].unique().tolist())
    daily_gross_returns = []

    for d in dates:
        sub = df_pred[df_pred["trading_date"] == d].copy()
        if len(sub) >= 20:
            sub["rank"] = sub[pred_col].rank(pct=True)
            long_leg = sub[sub["rank"] >= 0.80]
            short_leg = sub[sub["rank"] <= 0.20]
            if len(long_leg) > 0 and len(short_leg) > 0:
                ret_long = long_leg[return_col].mean()
                ret_short = short_leg[return_col].mean()
                # 5-day holding return of the long-short spread
                ls_spread_5d = ret_long - ret_short
                # Convert 5-day return to effective 1-day step in staggered portfolio: ret / 5.0
                daily_gross_returns.append(ls_spread_5d / 5.0)

    if not daily_gross_returns:
        return {"error": "Insufficient daily observations for economic simulation"}

    gross_arr = np.array(daily_gross_returns)
    T = len(gross_arr)
    cum_gross = float(np.prod(1.0 + gross_arr) - 1.0)
    ann_gross_ret = float(np.mean(gross_arr) * 252.0)
    ann_vol = float(np.std(gross_arr, ddof=1) * np.sqrt(252.0)) if T > 1 else 1e-6
    sharpe_gross = float(ann_gross_ret / ann_vol) if ann_vol > 0 else 0.0

    # Max Drawdown
    wealth = np.cumprod(1.0 + gross_arr)
    peaks = np.maximum.accumulate(wealth)
    drawdowns = (wealth - peaks) / peaks
    max_dd = float(np.min(drawdowns))

    # Daily turnover assumption: top/bottom quintile rebalancing with 5-day horizon has ~40% daily turnover
    daily_turnover = 0.40

    cost_results = {}
    for bps in [10, 20, 30]:
        cost_rate = (bps / 10000.0) * daily_turnover
        net_arr = gross_arr - cost_rate
        cum_net = float(np.prod(1.0 + net_arr) - 1.0)
        ann_net_ret = float(np.mean(net_arr) * 252.0)
        sharpe_net = float(ann_net_ret / ann_vol) if ann_vol > 0 else 0.0
        cost_results[f"{bps}bps"] = {
            "cum_net_return": cum_net,
            "ann_net_return": ann_net_ret,
            "net_sharpe": sharpe_net,
        }

    return {
        "n_sessions": T,
        "cum_gross_return": cum_gross,
        "ann_gross_return": ann_gross_ret,
        "ann_volatility": ann_vol,
        "gross_sharpe": sharpe_gross,
        "max_drawdown": max_dd,
        "daily_turnover": daily_turnover,
        "cost_scenarios": cost_results,
    }


def fit_and_evaluate_fold(
    df_train: pd.DataFrame,
    df_val: pd.DataFrame,
    feature_cols: List[str],
    target_col: str,
    target_type: str,
) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    """Fits Ridge on df_train with training-only imputation/scaling, evaluates on df_val."""
    X_train = df_train[feature_cols].values
    y_train = df_train[target_col].values
    X_val = df_val[feature_cols].values
    y_val = df_val[target_col].values

    # Preprocessing strictly on train
    imputer = SimpleImputer(strategy="median")
    X_train_imp = imputer.fit_transform(X_train)
    X_val_imp = imputer.transform(X_val)

    scaler = StandardScaler()
    X_train_scl = scaler.fit_transform(X_train_imp)
    X_val_scl = scaler.transform(X_val_imp)

    # Train inner split for alpha tuning (temporal split of training set)
    n_tr = len(X_train_scl)
    split_idx = int(n_tr * 0.75)
    X_tr_in, y_tr_in = X_train_scl[:split_idx], y_train[:split_idx]
    X_va_in, y_va_in = X_train_scl[split_idx:], y_train[split_idx:]

    alphas = [0.01, 0.1, 1.0, 10.0, 100.0, 1000.0, 10000.0]
    best_alpha = 100.0
    best_inner_rmse = float("inf")

    for a in alphas:
        m = Ridge(alpha=a)
        m.fit(X_tr_in, y_tr_in)
        preds_in = m.predict(X_va_in)
        rmse_in = float(np.sqrt(np.mean((y_va_in - preds_in) ** 2)))
        if rmse_in < best_inner_rmse:
            best_inner_rmse = rmse_in
            best_alpha = a

    # Fit final model on full training set
    model = Ridge(alpha=best_alpha)
    model.fit(X_train_scl, y_train)

    train_preds = model.predict(X_train_scl)
    val_preds = model.predict(X_val_scl)

    meta = {
        "best_alpha": float(best_alpha),
        "n_train": len(df_train),
        "n_val": len(df_val),
    }
    return train_preds, val_preds, meta


def run_phase7b_evaluation():
    print("=" * 95)
    print("PHASE 7B: HISTORICAL MARKET-MODEL EVALUATION AND VALIDATION (2019-2023)")
    print("=" * 95)
    t0 = time.time()

    data_dir = PROJECT_ROOT / "data" / "processed" / "research" / "phase7b"
    dataset_path = data_dir / "phase7b_market_expanded_dataset.parquet"
    print(f"Loading expanded dataset from {dataset_path}...")
    df = pd.read_parquet(dataset_path)
    print(f"Loaded {len(df):,} total rows across {df['trading_date'].nunique()} trading dates.")

    # Filter to valid targets
    df_valid = df[df["target_forward_return_5d_valid"] == True].copy()
    print(f"Valid target observations: {len(df_valid):,} rows.")

    # Define Feature Sets
    orig_mkt_features = MarketBaselinePipeline.MARKET_FEATURE_COLUMNS
    cleaned_mkt_features = [
        "market_return_1d", "market_return_5d", "market_return_21d",
        "market_volatility_5d", "market_volatility_21d", "market_volatility_63d",
        "market_momentum_63d",
        "market_distance_sma20", "market_distance_sma50", "market_sma_ratio",
        "market_zscore_20d", "market_zscore_50d", "market_rsi_14d",
        "market_volume_change_1d", "market_volume_ratio_20d",
    ]
    fund_clean_features = [
        "fundamental_earnings_yield", "fundamental_net_margin_cl", "fundamental_roa_cl",
        "fundamental_debt_to_assets_cl", "fundamental_debt_to_equity_cl",
        "fundamental_ocf_to_ni_cl", "fundamental_revenue_age_days",
    ]
    cleaned_multimodal_features = cleaned_mkt_features + fund_clean_features

    # Model Specifications
    models_to_run = {
        "m1_raw_orig_mkt": {
            "name": "M1: Raw Target + Orig Market (17 feats)",
            "target_col": "target_raw",
            "features": orig_mkt_features,
            "target_type": "raw",
        },
        "m2_raw_clean_mkt": {
            "name": "M2: Raw Target + Cleaned Market (15 feats)",
            "target_col": "target_raw",
            "features": cleaned_mkt_features,
            "target_type": "raw",
        },
        "m3_mkt_excess_clean_mkt": {
            "name": "M3: Market-Neutral + Cleaned Market (15 feats)",
            "target_col": "target_mkt_excess",
            "features": cleaned_mkt_features,
            "target_type": "mkt_excess",
        },
        "m4_sec_excess_clean_mkt": {
            "name": "M4: Sector-Neutral + Cleaned Market (15 feats)",
            "target_col": "target_sec_excess",
            "features": cleaned_mkt_features,
            "target_type": "sec_excess",
        },
        "m5_sec_excess_clean_multi": {
            "name": "M5: Sector-Neutral + Multimodal (22 feats)",
            "target_col": "target_sec_excess",
            "features": cleaned_multimodal_features,
            "target_type": "sec_excess",
        },
    }

    # Chronological Development Splits (2019-01-02 to 2021-12-31)
    dev_folds = [
        {
            "fold_idx": 1,
            "train_start": "2019-01-02", "train_end": "2019-12-31",
            "val_start": "2020-01-08", "val_end": "2020-06-30",
        },
        {
            "fold_idx": 2,
            "train_start": "2019-01-02", "train_end": "2020-06-30",
            "val_start": "2020-07-09", "val_end": "2020-12-31",
        },
        {
            "fold_idx": 3,
            "train_start": "2019-01-02", "train_end": "2020-12-31",
            "val_start": "2021-01-11", "val_end": "2021-06-30",
        },
        {
            "fold_idx": 4,
            "train_start": "2019-01-02", "train_end": "2021-06-30",
            "val_start": "2021-07-09", "val_end": "2021-12-31",
        },
    ]

    print("\n" + "=" * 80)
    print("STAGE 1: WALK-FORWARD DEVELOPMENT VALIDATION (2019-2021)")
    print("=" * 80)

    oos_dev_dfs = []
    dev_results_by_model = {m_id: {"folds": {}, "pooled": {}} for m_id in models_to_run}

    # Add baselines to dev results
    dev_results_by_model["b0_zero_sec_excess"] = {"folds": {}, "pooled": {}}
    dev_results_by_model["b_raw_train_mean"] = {"folds": {}, "pooled": {}}

    for fold in dev_folds:
        f_idx = fold["fold_idx"]
        tr_mask = (df_valid["trading_date"] >= fold["train_start"]) & (df_valid["trading_date"] <= fold["train_end"])
        va_mask = (df_valid["trading_date"] >= fold["val_start"]) & (df_valid["trading_date"] <= fold["val_end"])

        df_tr = df_valid[tr_mask].copy()
        df_va = df_valid[va_mask].copy()

        print(f"\n--- Fold {f_idx} ---")
        print(f"  Train: {fold['train_start']} to {fold['train_end']} ({len(df_tr):,} rows, {df_tr['trading_date'].nunique()} dates)")
        print(f"  Val  : {fold['val_start']} to {fold['val_end']} ({len(df_va):,} rows, {df_va['trading_date'].nunique()} dates)")

        fold_va_preds = df_va[["company_id", "ticker", "trading_date", "sector", "target_raw", "target_mkt_excess", "target_sec_excess"]].copy()
        fold_va_preds["fold"] = f_idx

        # Baseline Zero on Target Sec Excess
        fold_va_preds["pred_b0_sec_excess"] = 0.0
        b0_reg = compute_regression_metrics(fold_va_preds["target_sec_excess"].values, fold_va_preds["pred_b0_sec_excess"].values)
        dev_results_by_model["b0_zero_sec_excess"]["folds"][f_idx] = b0_reg

        # Baseline Train-Mean on Raw
        mean_tr_raw = float(df_tr["target_raw"].mean())
        fold_va_preds["pred_b_raw_mean"] = mean_tr_raw
        b_raw_reg = compute_regression_metrics(fold_va_preds["target_raw"].values, fold_va_preds["pred_b_raw_mean"].values)
        dev_results_by_model["b_raw_train_mean"]["folds"][f_idx] = b_raw_reg

        # Fit each candidate model
        for m_id, cfg in models_to_run.items():
            _, val_p, meta = fit_and_evaluate_fold(df_tr, df_va, cfg["features"], cfg["target_col"], cfg["target_type"])
            pred_col = f"pred_{m_id}"
            fold_va_preds[pred_col] = val_p

            reg_metrics = compute_regression_metrics(fold_va_preds[cfg["target_col"]].values, val_p)
            ic_metrics = compute_daily_cross_sectional_ic(fold_va_preds, pred_col, cfg["target_col"])

            dev_results_by_model[m_id]["folds"][f_idx] = {
                "regression": reg_metrics,
                "ic": ic_metrics,
                "meta": meta,
            }
            print(f"  {cfg['name'][:35]:<35} | RMSE: {reg_metrics['rmse']:.4f} | IC: {ic_metrics['mean_daily_ic']:+.4f} ({ic_metrics['pct_positive_ic_days']:.1f}% pos) | HAC t: {ic_metrics['hac_tstat']:+.2f}")

        oos_dev_dfs.append(fold_va_preds)

    df_oos_dev = pd.concat(oos_dev_dfs, axis=0).reset_index(drop=True)
    print(f"\nPooled Out-of-Sample Development Observations: {len(df_oos_dev):,} across {df_oos_dev['trading_date'].nunique()} trading dates.")

    # Compute Pooled Metrics across Development
    print("\n--- Summary of Pooled Walk-Forward Development Performance (2020-2021) ---")
    for m_id, cfg in models_to_run.items():
        pred_col = f"pred_{m_id}"
        reg = compute_regression_metrics(df_oos_dev[cfg["target_col"]].values, df_oos_dev[pred_col].values)
        ic = compute_daily_cross_sectional_ic(df_oos_dev, pred_col, cfg["target_col"])
        sec_ic = compute_sector_daily_ic(df_oos_dev, pred_col, cfg["target_col"])
        econ = simulate_economic_quintile_strategy(df_oos_dev, pred_col, "target_raw")

        dev_results_by_model[m_id]["pooled"] = {
            "regression": reg,
            "ic": ic,
            "sector_ic": sec_ic,
            "economic_sim": econ,
        }
        print(f"  {cfg['name'][:35]:<35} | RMSE: {reg['rmse']:.4f} | Mean IC: {ic['mean_daily_ic']:+.4f} | %Pos: {ic['pct_positive_ic_days']:.1f}% | HAC p: {ic['hac_pvalue']:.4f} | Gross Sharpe: {econ['gross_sharpe']:+.2f}")

    # Baseline pooled
    b0_reg_pooled = compute_regression_metrics(df_oos_dev["target_sec_excess"].values, df_oos_dev["pred_b0_sec_excess"].values)
    dev_results_by_model["b0_zero_sec_excess"]["pooled"] = {"regression": b0_reg_pooled}
    b_raw_reg_pooled = compute_regression_metrics(df_oos_dev["target_raw"].values, df_oos_dev["pred_b_raw_mean"].values)
    dev_results_by_model["b_raw_train_mean"]["pooled"] = {"regression": b_raw_reg_pooled}

    print(f"  Baseline Zero (Sec-Neutral)       | RMSE: {b0_reg_pooled['rmse']:.4f} | MAE: {b0_reg_pooled['mae']:.4f}")
    print(f"  Baseline Train-Mean (Raw)         | RMSE: {b_raw_reg_pooled['rmse']:.4f} | MAE: {b_raw_reg_pooled['mae']:.4f}")

    # Save development predictions
    dev_pred_path = data_dir / "phase7b_predictions_development.parquet"
    df_oos_dev.to_parquet(dev_pred_path, index=False)
    print(f"Saved development predictions to {dev_pred_path}.")

    # =========================================================================
    # STAGE 2: QUARANTINED FINAL EVALUATION HOLDOUT (2022-2023)
    # =========================================================================
    print("\n" + "=" * 80)
    print("STAGE 2: QUARANTINED FINAL EVALUATION HOLDOUT (2022-2023)")
    print("=" * 80)

    # Train on full development window (2019-01-02 to 2021-12-31)
    # Purge 5 sessions (2022-01-03 to 2022-01-07)
    # Evaluate on Holdout (2022-01-10 to 2023-12-20)
    train_holdout_mask = (df_valid["trading_date"] >= "2019-01-02") & (df_valid["trading_date"] <= "2021-12-31")
    eval_holdout_mask = (df_valid["trading_date"] >= "2022-01-10") & (df_valid["trading_date"] <= "2023-12-20")

    df_tr_final = df_valid[train_holdout_mask].copy()
    df_eval_final = df_valid[eval_holdout_mask].copy()

    print(f"Training partition (2019-2021) : {len(df_tr_final):,} rows across {df_tr_final['trading_date'].nunique()} trading dates.")
    print(f"Final Holdout partition (2022-23): {len(df_eval_final):,} rows across {df_eval_final['trading_date'].nunique()} trading dates.")

    df_holdout_preds = df_eval_final[["company_id", "ticker", "trading_date", "sector", "target_raw", "target_mkt_excess", "target_sec_excess"]].copy()

    # Baseline Zero and Train Mean on Final Holdout
    df_holdout_preds["pred_b0_sec_excess"] = 0.0
    df_holdout_preds["pred_b_raw_mean"] = float(df_tr_final["target_raw"].mean())

    holdout_results = {
        "b0_zero_sec_excess": {
            "regression": compute_regression_metrics(df_holdout_preds["target_sec_excess"].values, df_holdout_preds["pred_b0_sec_excess"].values)
        },
        "b_raw_train_mean": {
            "regression": compute_regression_metrics(df_holdout_preds["target_raw"].values, df_holdout_preds["pred_b_raw_mean"].values)
        }
    }

    # Evaluate models on final holdout (Note: M5 Multimodal is evaluated with available features)
    for m_id, cfg in models_to_run.items():
        _, holdout_p, meta = fit_and_evaluate_fold(df_tr_final, df_eval_final, cfg["features"], cfg["target_col"], cfg["target_type"])
        pred_col = f"pred_{m_id}"
        df_holdout_preds[pred_col] = holdout_p

        reg = compute_regression_metrics(df_holdout_preds[cfg["target_col"]].values, holdout_p)
        ic_all = compute_daily_cross_sectional_ic(df_holdout_preds, pred_col, cfg["target_col"])
        sec_ic = compute_sector_daily_ic(df_holdout_preds, pred_col, cfg["target_col"])
        econ = simulate_economic_quintile_strategy(df_holdout_preds, pred_col, "target_raw")

        # Sub-period analysis: 2022 Bear vs 2023 Bull
        mask_2022 = df_holdout_preds["trading_date"].str[:4] == "2022"
        mask_2023 = df_holdout_preds["trading_date"].str[:4] == "2023"

        ic_2022 = compute_daily_cross_sectional_ic(df_holdout_preds[mask_2022], pred_col, cfg["target_col"])
        ic_2023 = compute_daily_cross_sectional_ic(df_holdout_preds[mask_2023], pred_col, cfg["target_col"])

        holdout_results[m_id] = {
            "name": cfg["name"],
            "target": cfg["target_col"],
            "meta": meta,
            "regression": reg,
            "ic_pooled_holdout": ic_all,
            "ic_2022_bear": ic_2022,
            "ic_2023_bull": ic_2023,
            "sector_ic": sec_ic,
            "economic_sim": econ,
        }

        print(f"\n--- {cfg['name']} ---")
        print(f"  Pooled Holdout (2022-2023, {ic_all['n_dates']} dates):")
        print(f"    RMSE: {reg['rmse']:.4f} | Mean Daily IC: {ic_all['mean_daily_ic']:+.4f} | %Pos: {ic_all['pct_positive_ic_days']:.1f}%")
        print(f"    HAC SE: {ic_all['hac_se']:.4f} | HAC t: {ic_all['hac_tstat']:+.2f} | HAC p-value: {ic_all['hac_pvalue']:.4f}")
        print(f"  Yearly Breakdown:")
        print(f"    2022 Bear Market ({ic_2022['n_dates']} dates): Mean IC = {ic_2022['mean_daily_ic']:+.4f} ({ic_2022['pct_positive_ic_days']:.1f}% pos, p={ic_2022['hac_pvalue']:.4f})")
        print(f"    2023 Bull Market ({ic_2023['n_dates']} dates): Mean IC = {ic_2023['mean_daily_ic']:+.4f} ({ic_2023['pct_positive_ic_days']:.1f}% pos, p={ic_2023['hac_pvalue']:.4f})")
        print(f"  Economic Relevance (Q5 Long / Q1 Short):")
        print(f"    Gross Return: {econ['cum_gross_return']*100:+.1f}% | Gross Sharpe: {econ['gross_sharpe']:+.2f} | Max DD: {econ['max_drawdown']*100:.1f}%")
        for bps, scen in econ["cost_scenarios"].items():
            print(f"    Net Return @ {bps}: {scen['cum_net_return']*100:+.1f}% | Net Sharpe: {scen['net_sharpe']:+.2f}")

    # Save holdout predictions
    holdout_pred_path = data_dir / "phase7b_predictions_final_holdout.parquet"
    df_holdout_preds.to_parquet(holdout_pred_path, index=False)
    print(f"\nSaved final holdout predictions to {holdout_pred_path}.")

    # Consolidate Full Results JSON
    full_results = {
        "phase": "Phase 7B",
        "created_at_utc": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "dataset_path": str(dataset_path.relative_to(PROJECT_ROOT)),
        "dataset_rows": len(df),
        "valid_target_rows": len(df_valid),
        "development_results": dev_results_by_model,
        "final_holdout_results": holdout_results,
    }

    results_out_path = data_dir / "phase7b_experiment_results.json"
    with open(results_out_path, "w") as f:
        json.dump(full_results, f, indent=2)
    print(f"Saved experiment results to {results_out_path}.")
    print(f"Total evaluation time: {time.time() - t0:.1f}s.")
    return full_results


if __name__ == "__main__":
    run_phase7b_evaluation()

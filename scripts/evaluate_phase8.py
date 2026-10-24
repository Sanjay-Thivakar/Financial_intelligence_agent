"""
Phase 8F, 8G, 8H — Specialist Model 3 Development, Like-for-Like Evaluation & Economic Relevance.

Executes the formal research protocol for the Financial Reports Intelligence Model:
1. Baselines: Zero excess return and Train-Mean.
2. Market-Only Baseline: Frozen M4 Cleaned Market (15 features).
3. Model 3 Specialist: Pure Financial Reports Model (15 financial features).
4. Model 3 Combined: Market + Financial Reports Model (30 features).

Protocols:
- Strict walk-forward evaluation (Folds 1-4: 2019-2021) with 5-session purge gaps.
- Reused historical holdout (2022-2023) with 5-session purge gap.
- Matched-cohort comparison isolating incremental contribution of financial reports.
- Dependence-aware inference: Daily cross-sectional Spearman IC with Newey-West HAC (L=4).
- Paired statistical test for incremental delta: Delta IC = IC_combined - IC_market.
- Economic simulation: Q5 Long / Q1 Short with 10, 20, 30 bps friction.
- Non-destructive outputs saved to data/processed/research/phase8/.
"""

import json
import os
import sys
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

DATASET_PATH = PROJECT_ROOT / "data" / "processed" / "research" / "phase8" / "phase8_point_in_time_dataset.parquet"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "research" / "phase8"


def compute_regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
    mae = float(np.mean(np.abs(y_true - y_pred)))
    valid_mask = (y_true != 0) & (y_pred != 0)
    hit_rate = float(np.mean(np.sign(y_true[valid_mask]) == np.sign(y_pred[valid_mask]))) if valid_mask.sum() > 0 else 0.5
    return {"rmse": rmse, "mae": mae, "hit_rate": hit_rate}


def compute_daily_cross_sectional_ic(df_pred: pd.DataFrame, pred_col: str, target_col: str) -> Dict[str, Any]:
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
            "daily_ics": {},
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
        "daily_ics": dict(daily_records),
    }


def compute_paired_ic_difference(
    daily_ics_a: Dict[str, float],
    daily_ics_b: Dict[str, float],
) -> Dict[str, Any]:
    """Computes paired difference (Model B - Model A) across identical trading dates with HAC."""
    common_dates = sorted(set(daily_ics_a.keys()).intersection(set(daily_ics_b.keys())))
    if len(common_dates) < 10:
        return {"n_dates": len(common_dates), "delta_mean_ic": 0.0, "hac_pvalue": 1.0}

    diffs = np.array([daily_ics_b[d] - daily_ics_a[d] for d in common_dates])
    T = len(diffs)
    mean_diff = float(np.mean(diffs))
    median_diff = float(np.median(diffs))
    pct_improved = float(np.mean(diffs > 0) * 100.0)

    gamma_0 = float(np.var(diffs, ddof=1)) if T > 1 else 0.0
    L = 4
    if T > L:
        gammas = [float(np.cov(diffs[:-l], diffs[l:])[0, 1]) for l in range(1, L + 1)]
        v_hac = gamma_0 + 2.0 * sum((1.0 - (l / (L + 1.0))) * gammas[l - 1] for l in range(1, L + 1))
    else:
        v_hac = gamma_0

    se_hac = float(np.sqrt(max(v_hac, 1e-12) / T)) if T > 0 else 0.0
    t_hac = float(mean_diff / se_hac) if se_hac > 0 else 0.0
    p_hac = float(2.0 * (1.0 - t.cdf(abs(t_hac), df=max(T - 1, 1)))) if se_hac > 0 else 1.0

    return {
        "n_dates": T,
        "delta_mean_ic": mean_diff,
        "delta_median_ic": median_diff,
        "pct_improved_dates": pct_improved,
        "delta_hac_se": se_hac,
        "delta_hac_tstat": t_hac,
        "delta_hac_pvalue": p_hac,
    }


def compute_sector_daily_ic(df_pred: pd.DataFrame, pred_col: str, target_col: str) -> Dict[str, Dict[str, float]]:
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
                ls_spread_5d = ret_long - ret_short
                daily_gross_returns.append(ls_spread_5d / 5.0)

    if not daily_gross_returns:
        return {"error": "Insufficient daily observations"}

    gross_arr = np.array(daily_gross_returns)
    T = len(gross_arr)
    cum_gross = float(np.prod(1.0 + gross_arr) - 1.0)
    ann_gross_ret = float(np.mean(gross_arr) * 252.0)
    ann_vol = float(np.std(gross_arr, ddof=1) * np.sqrt(252.0)) if T > 1 else 1e-6
    sharpe_gross = float(ann_gross_ret / ann_vol) if ann_vol > 0 else 0.0

    wealth = np.cumprod(1.0 + gross_arr)
    peaks = np.maximum.accumulate(wealth)
    drawdowns = (wealth - peaks) / peaks
    max_dd = float(np.min(drawdowns))

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
) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    X_train = df_train[feature_cols].values
    y_train = df_train[target_col].values
    X_val = df_val[feature_cols].values

    # Preprocessing strictly on train
    imputer = SimpleImputer(strategy="median")
    X_train_imp = imputer.fit_transform(X_train)
    X_val_imp = imputer.transform(X_val)

    scaler = StandardScaler()
    X_train_scl = scaler.fit_transform(X_train_imp)
    X_val_scl = scaler.transform(X_val_imp)

    # Inner temporal split on train for alpha selection
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

    # Fit final Ridge on full training set
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


def run_phase8_evaluation():
    print("=" * 95)
    print("PHASE 8F & 8G: FINANCIAL REPORTS MODEL DEVELOPMENT & LIKE-FOR-LIKE EVALUATION")
    print("=" * 95)
    t0 = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Loading Phase 8 dataset from {DATASET_PATH}...")
    df = pd.read_parquet(DATASET_PATH)
    print(f"Loaded {len(df):,} total rows.")

    # Target: Sector-Neutral 5-Session Excess Return
    target_col = "target_sec_excess"

    # Define Feature Sets
    cleaned_mkt_features = [
        "market_return_1d", "market_return_5d", "market_return_21d",
        "market_volatility_5d", "market_volatility_21d", "market_volatility_63d",
        "market_momentum_63d",
        "market_distance_sma20", "market_distance_sma50", "market_sma_ratio",
        "market_zscore_20d", "market_zscore_50d", "market_rsi_14d",
        "market_volume_change_1d", "market_volume_ratio_20d",
    ]

    financial_features = [
        "fin_gross_margin", "fin_operating_margin", "fin_net_margin",
        "fin_roa", "fin_roe", "fin_debt_to_assets", "fin_debt_to_equity",
        "fin_current_ratio", "fin_cash_to_assets", "fin_ocf_to_assets",
        "fin_fcf_to_assets", "fin_ocf_to_net_income", "fin_accruals",
        "fin_earnings_yield", "fin_filing_age_days",
    ]

    combined_features = cleaned_mkt_features + financial_features

    print(f"Feature set sizes: Market={len(cleaned_mkt_features)}, Financials={len(financial_features)}, Combined={len(combined_features)}")

    # Model Specifications
    models_to_run = {
        "m_market_only": {
            "name": "Market Baseline (Frozen M4)",
            "features": cleaned_mkt_features,
        },
        "m_financial_specialist": {
            "name": "Model 3: Financial Reports Specialist",
            "features": financial_features,
        },
        "m_combined": {
            "name": "Model 3: Combined Market + Financials",
            "features": combined_features,
        },
    }

    # Chronological Development Folds (2019-2021)
    dev_folds = [
        {"fold_idx": 1, "train_start": "2019-01-02", "train_end": "2019-12-31", "val_start": "2020-01-08", "val_end": "2020-06-30"},
        {"fold_idx": 2, "train_start": "2019-01-02", "train_end": "2020-06-30", "val_start": "2020-07-09", "val_end": "2020-12-31"},
        {"fold_idx": 3, "train_start": "2019-01-02", "train_end": "2020-12-31", "val_start": "2021-01-11", "val_end": "2021-06-30"},
        {"fold_idx": 4, "train_start": "2019-01-02", "train_end": "2021-06-30", "val_start": "2021-07-09", "val_end": "2021-12-31"},
    ]

    # Filter to MATCHED COHORT for fair like-for-like comparison
    # Both market features and core fresh financial features are valid
    df_eval = df[df["eval_eligible_matched"] == True].copy()
    print(f"Matched Evaluation Panel: {len(df_eval):,} observations ({len(df_eval)/len(df)*100:.1f}% of total).")

    # =========================================================================
    # STAGE 1: WALK-FORWARD DEVELOPMENT (2020-2021)
    # =========================================================================
    print("\n" + "=" * 80)
    print("STAGE 1: WALK-FORWARD DEVELOPMENT (4 FOLDS, 2020-2021)")
    print("=" * 80)

    oos_dev_dfs = []
    dev_results_by_model = {m_id: {"folds": {}, "pooled": {}} for m_id in models_to_run}

    for fold in dev_folds:
        f_idx = fold["fold_idx"]
        tr_mask = (df_eval["trading_date"] >= fold["train_start"]) & (df_eval["trading_date"] <= fold["train_end"])
        va_mask = (df_eval["trading_date"] >= fold["val_start"]) & (df_eval["trading_date"] <= fold["val_end"])

        df_tr = df_eval[tr_mask].copy()
        df_va = df_eval[va_mask].copy()

        print(f"\n--- Fold {f_idx} ---")
        print(f"  Train: {fold['train_start']} to {fold['train_end']} ({len(df_tr):,} rows)")
        print(f"  Val  : {fold['val_start']} to {fold['val_end']} ({len(df_va):,} rows)")

        fold_preds = df_va[["company_id", "ticker", "trading_date", "sector", "target_raw", "target_sec_excess"]].copy()
        fold_preds["fold"] = f_idx

        # Fit each candidate model
        for m_id, cfg in models_to_run.items():
            _, val_p, meta = fit_and_evaluate_fold(df_tr, df_va, cfg["features"], target_col)
            pred_col = f"pred_{m_id}"
            fold_preds[pred_col] = val_p

            reg = compute_regression_metrics(fold_preds[target_col].values, val_p)
            ic = compute_daily_cross_sectional_ic(fold_preds, pred_col, target_col)

            dev_results_by_model[m_id]["folds"][f_idx] = {
                "regression": reg,
                "ic": {k: v for k, v in ic.items() if k != "daily_ics"},
                "meta": meta,
            }
            print(f"  {cfg['name'][:38]:<38} | RMSE: {reg['rmse']:.4f} | IC: {ic['mean_daily_ic']:+.4f} ({ic['pct_positive_ic_days']:.1f}% pos) | HAC t: {ic['hac_tstat']:+.2f}")

        oos_dev_dfs.append(fold_preds)

    df_oos_dev = pd.concat(oos_dev_dfs, axis=0).reset_index(drop=True)
    print(f"\nPooled Dev Observations: {len(df_oos_dev):,} across {df_oos_dev['trading_date'].nunique()} trading dates.")

    # Pooled dev summary
    print("\n--- Summary of Pooled Walk-Forward Development Performance (2020-2021) ---")
    model_ics_dev = {}
    for m_id, cfg in models_to_run.items():
        pred_col = f"pred_{m_id}"
        reg = compute_regression_metrics(df_oos_dev[target_col].values, df_oos_dev[pred_col].values)
        ic = compute_daily_cross_sectional_ic(df_oos_dev, pred_col, target_col)
        sec_ic = compute_sector_daily_ic(df_oos_dev, pred_col, target_col)
        econ = simulate_economic_quintile_strategy(df_oos_dev, pred_col, "target_raw")
        model_ics_dev[m_id] = ic["daily_ics"]

        dev_results_by_model[m_id]["pooled"] = {
            "regression": reg,
            "ic": {k: v for k, v in ic.items() if k != "daily_ics"},
            "sector_ic": sec_ic,
            "economic_sim": econ,
        }
        print(f"  {cfg['name'][:38]:<38} | RMSE: {reg['rmse']:.4f} | Mean IC: {ic['mean_daily_ic']:+.4f} | %Pos: {ic['pct_positive_ic_days']:.1f}% | HAC p: {ic['hac_pvalue']:.4f} | Gross Sharpe: {econ['gross_sharpe']:+.2f}")

    # Compute Dev Incremental Paired Difference: Combined vs Market-Only
    delta_dev = compute_paired_ic_difference(model_ics_dev["m_market_only"], model_ics_dev["m_combined"])
    print(f"\n  [DEV] Incremental Gain (Combined - Market Baseline):")
    print(f"    Delta Mean IC = {delta_dev['delta_mean_ic']:+.5f} | HAC t = {delta_dev['delta_hac_tstat']:+.2f} | HAC p-value = {delta_dev['delta_hac_pvalue']:.4f} | % Improved Days = {delta_dev['pct_improved_dates']:.1f}%")

    # Save dev predictions
    dev_pred_path = OUTPUT_DIR / "phase8_predictions_development.parquet"
    df_oos_dev.to_parquet(dev_pred_path, index=False)
    print(f"Saved development predictions to {dev_pred_path.relative_to(PROJECT_ROOT)}.")

    # =========================================================================
    # STAGE 2: REUSED HISTORICAL EVALUATION HOLDOUT (2022-2023)
    # =========================================================================
    print("\n" + "=" * 80)
    print("STAGE 2: REUSED HISTORICAL EVALUATION HOLDOUT (2022-2023)")
    print("=" * 80)

    train_holdout_mask = (df_eval["trading_date"] >= "2019-01-02") & (df_eval["trading_date"] <= "2021-12-31")
    eval_holdout_mask = (df_eval["trading_date"] >= "2022-01-10") & (df_eval["trading_date"] <= "2023-12-20")

    df_tr_final = df_eval[train_holdout_mask].copy()
    df_eval_final = df_eval[eval_holdout_mask].copy()

    print(f"Training partition (2019-2021) : {len(df_tr_final):,} rows across {df_tr_final['trading_date'].nunique()} trading dates.")
    print(f"Final Holdout partition (2022-23): {len(df_eval_final):,} rows across {df_eval_final['trading_date'].nunique()} trading dates.")

    df_holdout_preds = df_eval_final[["company_id", "ticker", "trading_date", "sector", "target_raw", "target_sec_excess"]].copy()

    holdout_results = {}
    model_ics_holdout = {}

    for m_id, cfg in models_to_run.items():
        _, holdout_p, meta = fit_and_evaluate_fold(df_tr_final, df_eval_final, cfg["features"], target_col)
        pred_col = f"pred_{m_id}"
        df_holdout_preds[pred_col] = holdout_p

        reg = compute_regression_metrics(df_holdout_preds[target_col].values, holdout_p)
        ic_all = compute_daily_cross_sectional_ic(df_holdout_preds, pred_col, target_col)
        sec_ic = compute_sector_daily_ic(df_holdout_preds, pred_col, target_col)
        econ = simulate_economic_quintile_strategy(df_holdout_preds, pred_col, "target_raw")
        model_ics_holdout[m_id] = ic_all["daily_ics"]

        # Yearly breakdown: 2022 Bear vs 2023 Bull
        mask_2022 = df_holdout_preds["trading_date"].str[:4] == "2022"
        mask_2023 = df_holdout_preds["trading_date"].str[:4] == "2023"

        ic_2022 = compute_daily_cross_sectional_ic(df_holdout_preds[mask_2022], pred_col, target_col)
        ic_2023 = compute_daily_cross_sectional_ic(df_holdout_preds[mask_2023], pred_col, target_col)

        holdout_results[m_id] = {
            "name": cfg["name"],
            "meta": meta,
            "regression": reg,
            "ic_pooled_holdout": {k: v for k, v in ic_all.items() if k != "daily_ics"},
            "ic_2022_bear": {k: v for k, v in ic_2022.items() if k != "daily_ics"},
            "ic_2023_bull": {k: v for k, v in ic_2023.items() if k != "daily_ics"},
            "sector_ic": sec_ic,
            "economic_sim": econ,
        }

        print(f"\n--- {cfg['name']} ---")
        print(f"  Pooled Holdout (2022-2023, {ic_all['n_dates']} dates):")
        print(f"    RMSE: {reg['rmse']:.4f} | Mean Daily IC: {ic_all['mean_daily_ic']:+.4f} | %Pos: {ic_all['pct_positive_ic_days']:.1f}%")
        print(f"    HAC SE: {ic_all['hac_se']:.4f} | HAC t: {ic_all['hac_tstat']:+.2f} | HAC p-value: {ic_all['hac_pvalue']:.4f}")
        print(f"  Yearly Breakdown:")
        print(f"    2022 Bear ({ic_2022['n_dates']} dates): Mean IC = {ic_2022['mean_daily_ic']:+.4f} ({ic_2022['pct_positive_ic_days']:.1f}% pos, p={ic_2022['hac_pvalue']:.4f})")
        print(f"    2023 Bull ({ic_2023['n_dates']} dates): Mean IC = {ic_2023['mean_daily_ic']:+.4f} ({ic_2023['pct_positive_ic_days']:.1f}% pos, p={ic_2023['hac_pvalue']:.4f})")
        print(f"  Economic Relevance (Q5 Long / Q1 Short):")
        print(f"    Gross Return: {econ['cum_gross_return']*100:+.1f}% | Gross Sharpe: {econ['gross_sharpe']:+.2f} | Max DD: {econ['max_drawdown']*100:.1f}%")
        for bps, scen in econ["cost_scenarios"].items():
            print(f"    Net Return @ {bps}: {scen['cum_net_return']*100:+.1f}% | Net Sharpe: {scen['net_sharpe']:+.2f}")

    # Compute Holdout Incremental Paired Difference: Combined vs Market-Only
    delta_holdout = compute_paired_ic_difference(model_ics_holdout["m_market_only"], model_ics_holdout["m_combined"])
    holdout_results["incremental_delta"] = delta_holdout

    print(f"\n" + "=" * 80)
    print("INCREMENTAL VALUE ANALYSIS (COMBINED vs MARKET BASELINE ON MATCHED COHORT)")
    print("=" * 80)
    print(f"  Pooled Holdout Delta Mean IC : {delta_holdout['delta_mean_ic']:+.5f}")
    print(f"  HAC Standard Error           : {delta_holdout['delta_hac_se']:.5f}")
    print(f"  HAC t-statistic              : {delta_holdout['delta_hac_tstat']:+.2f}")
    print(f"  HAC p-value                  : {delta_holdout['delta_hac_pvalue']:.4f}")
    print(f"  % Trading Days Improved      : {delta_holdout['pct_improved_dates']:.1f}%")

    # Save holdout predictions
    holdout_pred_path = OUTPUT_DIR / "phase8_predictions_final_holdout.parquet"
    df_holdout_preds.to_parquet(holdout_pred_path, index=False)
    print(f"\nSaved final holdout predictions to {holdout_pred_path.relative_to(PROJECT_ROOT)}.")

    # Save Full Machine-Readable Experiment Results
    experiment_results = {
        "phase": "Phase 8",
        "created_at_utc": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "dataset_path": str(DATASET_PATH.relative_to(PROJECT_ROOT)),
        "matched_cohort_rows": len(df_eval),
        "development_results": dev_results_by_model,
        "development_incremental_delta": delta_dev,
        "holdout_results": holdout_results,
    }

    results_out_path = OUTPUT_DIR / "phase8_experiment_results.json"
    with open(results_out_path, "w", encoding="utf-8") as f:
        json.dump(experiment_results, f, indent=2)
    print(f"Saved full experiment results to {results_out_path.relative_to(PROJECT_ROOT)}.")
    print(f"Total evaluation time: {time.time() - t0:.1f}s.")
    return experiment_results


if __name__ == "__main__":
    run_phase8_evaluation()

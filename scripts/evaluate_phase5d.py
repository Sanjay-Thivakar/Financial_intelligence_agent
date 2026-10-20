"""
Evaluation Script for Phase 5D: SEC Fundamentals Integration.

Evaluates and compares:
- Reference 0: Naive Zero Return
- Reference 1: Historical Median Return
- Model 1: Market-Only Ridge Baseline (Phase 5C)
- Model 2: Market + Fundamentals Ridge Baseline

Evaluates across:
1. Full 4-Company Panel (AAPL, JPM, GOOG, TSLA - 1,432 rows, 358 dates)
2. 2-Company Complete Fundamentals Cohort (AAPL, JPM - 716 rows, 358 dates)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from src.features.dataset import UnifiedDatasetBuilder, DatasetBuildConfig
from src.features.config import DecisionTimingMode, MarketFeatureConfig
from src.features.target import ForwardReturnTargetEngine, TargetConfig
from src.models.splitter import WalkForwardSplitter, WalkForwardConfig
from src.models.baseline import MarketBaselinePipeline


def run_experiment():
    df_market = pd.read_parquet("data/processed/market/sp500_market_sample.parquet")
    df_sec = pd.read_parquet("data/processed/sec/facts/pilot_financial_facts.parquet")

    cids = ["US_CIK_0000320193", "US_CIK_0000019617", "US_CIK_0001652044", "US_CIK_0001318605"]
    sub_market = df_market[
        (df_market["company_id"].isin(cids))
        & (df_market["trading_date"] >= "2019-01-01")
        & (df_market["trading_date"] <= "2020-06-10")
    ].copy()

    # Add 5-session forward return target
    target_engine = ForwardReturnTargetEngine(TargetConfig(horizon_sessions=5))
    sub_market = target_engine.add_target(sub_market)

    # Build unified dataset with fundamentals
    m_cfg = MarketFeatureConfig(decision_timing=DecisionTimingMode.NEXT_SESSION_OPEN)
    cfg = DatasetBuildConfig(market_config=m_cfg, pre_open_cutoff_minutes=15)
    builder = UnifiedDatasetBuilder(cfg)
    res = builder.build_dataset(sub_market, df_fundamentals=df_sec)
    df_unified = res.data[res.data["target_forward_return_5d_valid"]].copy()
    df_all = df_unified.sort_values(["trading_date", "company_id"]).reset_index(drop=True)

    f_features = [
        "fundamental_ratio_net_margin",
        "fundamental_ratio_roa",
        "fundamental_ratio_debt_to_assets",
        "fundamental_ratio_debt_to_equity",
        "fundamental_ratio_ocf_to_net_income",
        "fundamental_diluted_eps",
        "fundamental_revenue_age_days",
        "fundamental_all_facts_stale",
    ]
    market_features = MarketBaselinePipeline.FEATURE_COLUMNS
    combined_features = market_features + f_features

    # 1. 4-Company Panel Evaluation
    print("=" * 80)
    print("EXPERIMENT 1: FOUR-COMPANY PANEL (AAPL, JPM, GOOG, TSLA)")
    print(f"Total rows: {len(df_all)}, Unique dates: {df_all['trading_date'].nunique()}")
    print("=" * 80)

    wf_cfg_4 = WalkForwardConfig(n_splits=4, train_min_sessions=173, val_sessions=45, purge_sessions=5)
    splitter_4 = WalkForwardSplitter(wf_cfg_4)

    pipe_mkt = MarketBaselinePipeline(feature_columns=market_features)
    pipe_fund = MarketBaselinePipeline(feature_columns=combined_features)

    for fold, (tr_idx, val_idx) in enumerate(splitter_4.split(df_all)):
        tr_df, val_df = df_all.iloc[tr_idx], df_all.iloc[val_idx]
        y_tr, y_val = tr_df["target_forward_return_5d"].values, val_df["target_forward_return_5d"].values

        r_zero = pipe_mkt.evaluate_naive_zero(y_val)
        r_med = pipe_mkt.evaluate_naive_median(y_tr, y_val)
        r_mkt = pipe_mkt.fit_and_evaluate_ridge(tr_df, y_tr, val_df, y_val)
        r_fund = pipe_fund.fit_and_evaluate_ridge(tr_df, y_tr, val_df, y_val)

        tr_dates = sorted(tr_df["trading_date"].unique())
        val_dates = sorted(val_df["trading_date"].unique())
        print(f"\n--- FOLD {fold} ---")
        print(f"Train: {tr_dates[0]} -> {tr_dates[-1]} ({len(tr_df)} rows, {len(tr_dates)} dates)")
        print(f"Val:   {val_dates[0]} -> {val_dates[-1]} ({len(val_df)} rows, {len(val_dates)} dates)")
        print(f"Ref 0 (Zero):      RMSE={r_zero.rmse:.4f}, MAE={r_zero.mae:.4f}, Hit={r_zero.hit_rate*100:.2f}%")
        print(f"Ref 1 (Median):    RMSE={r_med.rmse:.4f}, MAE={r_med.mae:.4f}, Hit={r_med.hit_rate*100:.2f}%")
        print(f"Model 1 (Market):  RMSE={r_mkt.rmse:.4f}, MAE={r_mkt.mae:.4f}, Hit={r_mkt.hit_rate*100:.2f}%, IC={r_mkt.information_coefficient:.3f}, alpha={r_mkt.best_params['alpha']}")
        print(f"Model 2 (Mkt+Fund):RMSE={r_fund.rmse:.4f}, MAE={r_fund.mae:.4f}, Hit={r_fund.hit_rate*100:.2f}%, IC={r_fund.information_coefficient:.3f}, alpha={r_fund.best_params['alpha']}")

        # Per-company breakdown for Model 1 vs Model 2
        print("  Per-Company MAE / Hit Rate:")
        for tk in ["AAPL", "JPM", "GOOG", "TSLA"]:
            sub_mask = (val_df["ticker"] == tk).values
            y_sub = y_val[sub_mask]
            p_mkt_sub = r_mkt.predictions[sub_mask]
            p_fund_sub = r_fund.predictions[sub_mask]

            mae_mkt = np.mean(np.abs(y_sub - p_mkt_sub))
            hit_mkt = np.mean(np.sign(y_sub) == np.sign(p_mkt_sub))
            mae_fund = np.mean(np.abs(y_sub - p_fund_sub))
            hit_fund = np.mean(np.sign(y_sub) == np.sign(p_fund_sub))

            print(f"    {tk:4s}: Market MAE={mae_mkt:.4f} (Hit {hit_mkt*100:.1f}%) | Mkt+Fund MAE={mae_fund:.4f} (Hit {hit_fund*100:.1f}%)")

    # 2. 2-Company Complete Fundamentals Cohort Evaluation (AAPL & JPM)
    print("\n" + "=" * 80)
    print("EXPERIMENT 2: TWO-COMPANY COMPLETE FUNDAMENTALS COHORT (AAPL, JPM)")
    print("=" * 80)

    df_2 = df_all[df_all["ticker"].isin(["AAPL", "JPM"])].copy().sort_values(["trading_date", "company_id"]).reset_index(drop=True)
    print(f"Total rows: {len(df_2)}, Unique dates: {df_2['trading_date'].nunique()}")

    wf_cfg_2 = WalkForwardConfig(n_splits=4, train_min_sessions=173, val_sessions=45, purge_sessions=5)
    splitter_2 = WalkForwardSplitter(wf_cfg_2)

    for fold, (tr_idx, val_idx) in enumerate(splitter_2.split(df_2)):
        tr_df, val_df = df_2.iloc[tr_idx], df_2.iloc[val_idx]
        y_tr, y_val = tr_df["target_forward_return_5d"].values, val_df["target_forward_return_5d"].values

        r_zero = pipe_mkt.evaluate_naive_zero(y_val)
        r_med = pipe_mkt.evaluate_naive_median(y_tr, y_val)
        r_mkt = pipe_mkt.fit_and_evaluate_ridge(tr_df, y_tr, val_df, y_val)
        r_fund = pipe_fund.fit_and_evaluate_ridge(tr_df, y_tr, val_df, y_val)

        tr_dates = sorted(tr_df["trading_date"].unique())
        val_dates = sorted(val_df["trading_date"].unique())
        print(f"\n--- FOLD {fold} ---")
        print(f"Train: {tr_dates[0]} -> {tr_dates[-1]} ({len(tr_df)} rows, {len(tr_dates)} dates)")
        print(f"Val:   {val_dates[0]} -> {val_dates[-1]} ({len(val_df)} rows, {len(val_dates)} dates)")
        print(f"Ref 0 (Zero):      RMSE={r_zero.rmse:.4f}, MAE={r_zero.mae:.4f}, Hit={r_zero.hit_rate*100:.2f}%")
        print(f"Ref 1 (Median):    RMSE={r_med.rmse:.4f}, MAE={r_med.mae:.4f}, Hit={r_med.hit_rate*100:.2f}%")
        print(f"Model 1 (Market):  RMSE={r_mkt.rmse:.4f}, MAE={r_mkt.mae:.4f}, Hit={r_mkt.hit_rate*100:.2f}%, IC={r_mkt.information_coefficient:.3f}, alpha={r_mkt.best_params['alpha']}")
        print(f"Model 2 (Mkt+Fund):RMSE={r_fund.rmse:.4f}, MAE={r_fund.mae:.4f}, Hit={r_fund.hit_rate*100:.2f}%, IC={r_fund.information_coefficient:.3f}, alpha={r_fund.best_params['alpha']}")

        for tk in ["AAPL", "JPM"]:
            sub_mask = (val_df["ticker"] == tk).values
            y_sub = y_val[sub_mask]
            p_mkt_sub = r_mkt.predictions[sub_mask]
            p_fund_sub = r_fund.predictions[sub_mask]

            mae_mkt = np.mean(np.abs(y_sub - p_mkt_sub))
            hit_mkt = np.mean(np.sign(y_sub) == np.sign(p_mkt_sub))
            mae_fund = np.mean(np.abs(y_sub - p_fund_sub))
            hit_fund = np.mean(np.sign(y_sub) == np.sign(p_fund_sub))

            print(f"    {tk:4s}: Market MAE={mae_mkt:.4f} (Hit {hit_mkt*100:.1f}%) | Mkt+Fund MAE={mae_fund:.4f} (Hit {hit_fund*100:.1f}%)")


if __name__ == "__main__":
    run_experiment()

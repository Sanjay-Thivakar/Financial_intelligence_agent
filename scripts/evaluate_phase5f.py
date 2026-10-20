"""
Phase 5F — Comprehensive Walk-Forward Model Comparison Script.

Evaluates 6 model variants across the identical 4-fold walk-forward panel:
- Variant A: Reference 0 (Zero Return)
- Variant B: Reference 1 (Historical Median)
- Variant C: Model 1 (Market-Only Ridge, 17 features)
- Variant D: Model 2 (Market + Fundamentals Ridge, 25 features)
- Variant E: Model 3 (Market + SEC Events Ridge, 20 features)
- Variant F: Model 4 (Market + Fundamentals + SEC Events Ridge, 28 features)

Dataset: 4-Company Panel (AAPL, JPM, GOOG, TSLA)
Benchmark Window: 2019-01-01 to 2020-06-10
Valid Labeled Observations: 1,432 rows (358 dates x 4 companies)
Outer Folds: 4 chronological expanding folds, 45 sessions per validation fold (180 rows), 5-date purge gap.
Hyperparameter Tuning: Chronological date-based internal splits, strictly isolated preprocessing.
"""

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from src.features.dataset import UnifiedDatasetBuilder, DatasetBuildConfig
from src.features.config import DecisionTimingMode, MarketFeatureConfig
from src.features.target import ForwardReturnTargetEngine, TargetConfig
from src.models.splitter import WalkForwardSplitter, WalkForwardConfig
from src.models.baseline import MarketBaselinePipeline


def run_phase5f_evaluation():
    print("=" * 80)
    print("PHASE 5F — MULTI-MODAL WALK-FORWARD MODEL COMPARISON")
    print("=" * 80)

    # 1. Load Data
    df_market = pd.read_parquet("data/processed/market/sp500_market_sample.parquet")
    df_sec_facts = pd.read_parquet("data/processed/sec/facts/pilot_financial_facts.parquet")
    df_sec_events = pd.read_parquet("data/processed/sec/eight_k/phase5f_8k_events.parquet")
    df_universe = pd.read_parquet("data/processed/universe/sp500_universe.parquet")

    cids = ["US_CIK_0000320193", "US_CIK_0000019617", "US_CIK_0001652044", "US_CIK_0001318605"]
    sub_market = df_market[
        (df_market["company_id"].isin(cids))
        & (df_market["trading_date"] >= "2019-01-01")
        & (df_market["trading_date"] <= "2020-06-10")
    ].copy()

    # 2. Add 5-Session Forward Return Target (T close -> T+1 open to T+5 close)
    target_engine = ForwardReturnTargetEngine(TargetConfig(horizon_sessions=5))
    sub_market = target_engine.add_target(sub_market)

    # 3. Build Unified Multi-Modal Dataset
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
    print(f"Companies in Panel: {df_all['ticker'].unique().tolist()}")

    # Feature sets
    mkt_cols = MarketBaselinePipeline.MARKET_FEATURE_COLUMNS
    fund_cols = MarketBaselinePipeline.FUNDAMENTAL_FEATURE_COLUMNS
    event_cols = MarketBaselinePipeline.EVENT_FEATURE_COLUMNS
    mkt_fund_cols = mkt_cols + fund_cols
    mkt_event_cols = mkt_cols + event_cols
    all_cols = mkt_cols + fund_cols + event_cols

    print(f"Feature Set Sizes: Market={len(mkt_cols)}, Mkt+Fund={len(mkt_fund_cols)}, Mkt+Events={len(mkt_event_cols)}, All={len(all_cols)}")

    # 4. Set up Splitter (4 folds: min_T=173, val=45, purge=5)
    wf_cfg = WalkForwardConfig(n_splits=4, train_min_sessions=173, val_sessions=45, purge_sessions=5)
    splitter = WalkForwardSplitter(wf_cfg)

    # Pipelines
    pipe_mkt = MarketBaselinePipeline(feature_columns=mkt_cols)
    pipe_fund = MarketBaselinePipeline(feature_columns=mkt_fund_cols)
    pipe_event = MarketBaselinePipeline(feature_columns=mkt_event_cols)
    pipe_all = MarketBaselinePipeline(feature_columns=all_cols)

    fold_results = []

    for fold, (tr_idx, val_idx) in enumerate(splitter.split(df_all)):
        tr_df, val_df = df_all.iloc[tr_idx], df_all.iloc[val_idx]
        y_tr = tr_df["target_forward_return_5d"].values
        y_val = val_df["target_forward_return_5d"].values

        tr_dates = sorted(tr_df["trading_date"].unique())
        val_dates = sorted(val_df["trading_date"].unique())

        # Evaluate all 6 variants
        r_zero = pipe_mkt.evaluate_naive_zero(y_val)
        r_med = pipe_mkt.evaluate_naive_median(y_tr, y_val)
        r_mkt = pipe_mkt.fit_and_evaluate_ridge(tr_df, y_tr, val_df, y_val, model_name="Variant C (Market-Only Ridge)")
        r_fund = pipe_fund.fit_and_evaluate_ridge(tr_df, y_tr, val_df, y_val, model_name="Variant D (Market+Fund Ridge)")
        r_event = pipe_event.fit_and_evaluate_ridge(tr_df, y_tr, val_df, y_val, model_name="Variant E (Market+Events Ridge)")
        r_all = pipe_all.fit_and_evaluate_ridge(tr_df, y_tr, val_df, y_val, model_name="Variant F (Market+Fund+Events Ridge)")

        fold_dict = {
            "fold": fold,
            "train_start": tr_dates[0],
            "train_end": tr_dates[-1],
            "train_rows": len(tr_df),
            "train_dates_count": len(tr_dates),
            "val_start": val_dates[0],
            "val_end": val_dates[-1],
            "val_rows": len(val_df),
            "val_dates_count": len(val_dates),
            "models": {
                "Variant A (Zero Return)": {"rmse": r_zero.rmse, "mae": r_zero.mae, "hit_rate": r_zero.hit_rate, "ic": r_zero.information_coefficient, "alpha": None},
                "Variant B (Historical Median)": {"rmse": r_med.rmse, "mae": r_med.mae, "hit_rate": r_med.hit_rate, "ic": r_med.information_coefficient, "alpha": None},
                "Variant C (Market-Only Ridge)": {"rmse": r_mkt.rmse, "mae": r_mkt.mae, "hit_rate": r_mkt.hit_rate, "ic": r_mkt.information_coefficient, "alpha": r_mkt.best_params["alpha"]},
                "Variant D (Market+Fund Ridge)": {"rmse": r_fund.rmse, "mae": r_fund.mae, "hit_rate": r_fund.hit_rate, "ic": r_fund.information_coefficient, "alpha": r_fund.best_params["alpha"]},
                "Variant E (Market+Events Ridge)": {"rmse": r_event.rmse, "mae": r_event.mae, "hit_rate": r_event.hit_rate, "ic": r_event.information_coefficient, "alpha": r_event.best_params["alpha"]},
                "Variant F (Market+Fund+Events Ridge)": {"rmse": r_all.rmse, "mae": r_all.mae, "hit_rate": r_all.hit_rate, "ic": r_all.information_coefficient, "alpha": r_all.best_params["alpha"]},
            },
            "predictions": {
                "y_val": y_val.tolist(),
                "pred_zero": r_zero.predictions.tolist(),
                "pred_med": r_med.predictions.tolist(),
                "pred_mkt": r_mkt.predictions.tolist(),
                "pred_fund": r_fund.predictions.tolist(),
                "pred_event": r_event.predictions.tolist(),
                "pred_all": r_all.predictions.tolist(),
                "ticker": val_df["ticker"].tolist(),
                "trading_date": val_df["trading_date"].tolist(),
            }
        }
        fold_results.append(fold_dict)

        print(f"\n--- FOLD {fold} ---")
        print(f"Train: {tr_dates[0]} -> {tr_dates[-1]} ({len(tr_df)} rows, {len(tr_dates)} dates)")
        print(f"Val:   {val_dates[0]} -> {val_dates[-1]} ({len(val_df)} rows, {len(val_dates)} dates)")
        for m_name, m_res in fold_dict["models"].items():
            alpha_str = f", alpha={m_res['alpha']}" if m_res['alpha'] is not None else ""
            print(f"  {m_name:<36}: RMSE={m_res['rmse']:.4f}, MAE={m_res['mae']:.4f}, Hit={m_res['hit_rate']*100:.2f}%, IC={m_res['ic']:+.3f}{alpha_str}")

    # Aggregate Metrics Across All 4 Folds (N = 720 out-of-sample observations)
    print("\n" + "=" * 80)
    print("AGGREGATE OUT-OF-SAMPLE METRICS ACROSS ALL 4 FOLDS (N = 720 observations)")
    print("=" * 80)

    model_names = list(fold_results[0]["models"].keys())
    all_y_true = np.concatenate([np.array(f["predictions"]["y_val"]) for f in fold_results])

    agg_summary = {}
    for m_name in model_names:
        pred_key = {
            "Variant A (Zero Return)": "pred_zero",
            "Variant B (Historical Median)": "pred_med",
            "Variant C (Market-Only Ridge)": "pred_mkt",
            "Variant D (Market+Fund Ridge)": "pred_fund",
            "Variant E (Market+Events Ridge)": "pred_event",
            "Variant F (Market+Fund+Events Ridge)": "pred_all",
        }[m_name]

        all_y_pred = np.concatenate([np.array(f["predictions"][pred_key]) for f in fold_results])
        err = all_y_true - all_y_pred
        agg_rmse = float(np.sqrt(np.mean(err ** 2)))
        agg_mae = float(np.mean(np.abs(err)))

        valid_signs = (all_y_true != 0) & (all_y_pred != 0)
        hit_rate = float(np.mean(np.sign(all_y_true[valid_signs]) == np.sign(all_y_pred[valid_signs]))) if valid_signs.any() else 0.5
        ic, _ = spearmanr(all_y_pred, all_y_true) if not np.all(all_y_pred == all_y_pred[0]) else (0.0, 1.0)

        agg_summary[m_name] = {
            "agg_rmse": agg_rmse,
            "agg_mae": agg_mae,
            "agg_hit_rate": hit_rate,
            "agg_ic": float(ic),
        }
        print(f"  {m_name:<36}: RMSE={agg_rmse:.4f}, MAE={agg_mae:.4f}, Hit={hit_rate*100:.2f}%, IC={ic:+.3f}")

    # Per-Company Breakdown for Variant C vs Variant E (Market vs Market+Events)
    print("\n" + "=" * 80)
    print("PER-COMPANY BREAKDOWN: VARIANT C (Market) vs VARIANT E (Market + Events)")
    print("=" * 80)
    all_tickers = np.concatenate([np.array(f["predictions"]["ticker"]) for f in fold_results])
    all_pred_mkt = np.concatenate([np.array(f["predictions"]["pred_mkt"]) for f in fold_results])
    all_pred_evt = np.concatenate([np.array(f["predictions"]["pred_event"]) for f in fold_results])

    for tk in ["AAPL", "JPM", "GOOG", "TSLA"]:
        mask = (all_tickers == tk)
        y_tk = all_y_true[mask]
        p_mkt = all_pred_mkt[mask]
        p_evt = all_pred_evt[mask]

        mae_mkt = float(np.mean(np.abs(y_tk - p_mkt)))
        mae_evt = float(np.mean(np.abs(y_tk - p_evt)))
        hit_mkt = float(np.mean(np.sign(y_tk) == np.sign(p_mkt))) * 100.0
        hit_evt = float(np.mean(np.sign(y_tk) == np.sign(p_evt))) * 100.0
        ic_mkt, _ = spearmanr(p_mkt, y_tk)
        ic_evt, _ = spearmanr(p_evt, y_tk)

        delta_mae = mae_evt - mae_mkt
        status = "IMPROVED" if delta_mae < 0 else ("DEGRADED" if delta_mae > 0 else "IDENTICAL")
        print(f"  {tk:<5} (N={len(y_tk)}):")
        print(f"    Market-Only:    MAE={mae_mkt:.4f}, Hit={hit_mkt:.1f}%, IC={ic_mkt:+.3f}")
        print(f"    Market+Events:  MAE={mae_evt:.4f}, Hit={hit_evt:.1f}%, IC={ic_evt:+.3f}")
        print(f"    Delta MAE:      {delta_mae:+.5f} ({status})")

    # Save complete evaluation output
    out_dir = Path("data/processed/sec/eight_k")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_eval = out_dir / "phase5f_model_comparison_results.json"
    with open(out_eval, "w", encoding="utf-8") as f_out:
        # Save without raw arrays for compact audit
        clean_folds = []
        for fold_res in fold_results:
            clean_f = {k: v for k, v in fold_res.items() if k != "predictions"}
            clean_folds.append(clean_f)
        json.dump({"folds": clean_folds, "aggregate": agg_summary}, f_out, indent=2)
    print(f"\nSaved evaluation metrics artifact to: {out_eval}")


if __name__ == "__main__":
    run_phase5f_evaluation()

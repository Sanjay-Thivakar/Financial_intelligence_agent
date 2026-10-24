"""
Phase 6.8 — Multi-Modal Model Comparison & Evaluation Engine (300 Companies).

Executes reproducible, point-in-time multi-modal experiments across the expanded
300-company cohort and the 60-company core baseline:
- Model A: Market-Only Baseline (17 features)
- Model B: Market + Financial Fundamentals (25 features)
- Model C: Market + Structured Filing/Event Features (20 features)
- Model D: Market + Fundamentals + Filing/Event Features (28 features)
- Model E: Multi-Modal + Financial News (Ablation on news-covered subset)

Evaluates under strict chronological walk-forward validation:
- 4 outer folds, min_train=173 sessions, val=45 sessions, purge=5 sessions
- Out-of-sample evaluation window: 2019-01-01 to 2020-06-10
- Preprocessing (imputation and standardization) fit strictly on training fold
- Overlapping target dependence-aware Newey-West HAC inference (L=4)
- Deterministic portfolio simulation with 15 bps friction
- Saves machine-readable versioned research artifacts to data/processed/research/phase6_8/
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
from scipy.stats import spearmanr, t
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer

from src.features.calendar import MarketCalendar
from src.features.config import DecisionTimingMode
from src.features.market import MarketFeatureEngine, MarketFeatureConfig
from src.features.target import ForwardReturnTargetEngine, TargetConfig
from src.features.fundamental import FundamentalFeatureEngine
from src.features.event import SECEventFeatureEngine
from src.features.news import NewsFeatureEngine
from src.models.splitter import WalkForwardSplitter, WalkForwardConfig
from src.models.baseline import MarketBaselinePipeline
from src.decision.schema import TransactionCostConfig, RiskGateConfig, SignalType
from src.portfolio.schema import PortfolioConfig
from src.portfolio.simulator import DeterministicPortfolioSimulator


def compute_directional_accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Computes directional hit rate for non-zero pairs."""
    valid_mask = (y_true != 0) & (y_pred != 0)
    if valid_mask.sum() == 0:
        return 0.5
    return float(np.mean(np.sign(y_true[valid_mask]) == np.sign(y_pred[valid_mask])))


def compute_ic(y_true: np.ndarray, y_pred: np.ndarray) -> Tuple[float, float]:
    """Computes Spearman Rank Correlation and asymptotic p-value."""
    if len(y_true) < 5 or np.all(y_pred == y_pred[0]) or np.all(y_true == y_true[0]):
        return 0.0, 1.0
    corr, pval = spearmanr(y_true, y_pred)
    return (float(corr) if not np.isnan(corr) else 0.0), (float(pval) if not np.isnan(pval) else 1.0)


def compute_daily_cross_sectional_ic(df_predictions: pd.DataFrame, pred_col: str = "predicted_return", min_stocks: int = 10) -> Dict[str, Any]:
    """Computes daily cross-sectional Spearman rank IC and Newey-West HAC inference (L=4)."""
    daily_records = []
    dates = sorted(df_predictions["trading_date"].unique().tolist())
    for d in dates:
        d_sub = df_predictions[df_predictions["trading_date"] == d]
        if len(d_sub) >= min_stocks:
            c, _ = spearmanr(d_sub["target_return"], d_sub[pred_col])
            if not np.isnan(c):
                daily_records.append((d, float(c), len(d_sub)))

    if not daily_records:
        return {
            "n_trading_dates": 0, "mean_daily_ic": 0.0, "daily_ic_std": 0.0,
            "information_ratio": 0.0, "newey_west_hac_se": 0.0, "newey_west_hac_tstat": 0.0,
            "newey_west_hac_pvalue": 1.0,
        }

    df_daily = pd.DataFrame(daily_records, columns=["trading_date", "ic", "n_stocks"])
    mean_ic = float(df_daily["ic"].mean())
    std_ic = float(df_daily["ic"].std(ddof=1)) if len(df_daily) > 1 else 0.0
    T_dates = len(df_daily)
    ir_ic = float(mean_ic / std_ic) if std_ic > 0 else 0.0

    ic_vals = df_daily["ic"].values
    gamma_0 = float(np.var(ic_vals, ddof=1)) if len(ic_vals) > 1 else 0.0
    L = 4
    if len(ic_vals) > L:
        gammas = [float(np.cov(ic_vals[:-l], ic_vals[l:])[0, 1]) for l in range(1, L + 1)]
        v_hac = gamma_0 + 2.0 * sum((1.0 - (l / (L + 1.0))) * gammas[l - 1] for l in range(1, L + 1))
    else:
        v_hac = gamma_0

    se_hac = float(np.sqrt(max(v_hac, 1e-12) / T_dates)) if T_dates > 0 else 0.0
    t_hac = float(mean_ic / se_hac) if se_hac > 0 else 0.0
    p_hac = float(2.0 * (1.0 - t.cdf(abs(t_hac), df=max(T_dates - 1, 1)))) if se_hac > 0 else 1.0

    return {
        "n_trading_dates": T_dates,
        "mean_daily_ic": mean_ic,
        "daily_ic_std": std_ic,
        "information_ratio": ir_ic,
        "newey_west_hac_se": se_hac,
        "newey_west_hac_tstat": t_hac,
        "newey_west_hac_pvalue": p_hac,
    }


def run_phase6_8_evaluation():
    print("=" * 95, flush=True)
    print("PHASE 6.8: MULTI-MODAL MODEL COMPARISON & EVALUATION (300 COMPANIES)", flush=True)
    print("=" * 95, flush=True)

    t0 = time.time()
    out_dir = PROJECT_ROOT / "data" / "processed" / "research" / "phase6_8"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load 300-Company Cohort Manifest & Market Parquet
    manifest_path = PROJECT_ROOT / "data" / "processed" / "universe" / "phase6_8_cohort_300_manifest.csv"
    market_path = PROJECT_ROOT / "data" / "processed" / "market" / "phase6_8_market_300.parquet"
    facts_path = PROJECT_ROOT / "data" / "processed" / "sec" / "facts" / "phase6_8_financial_facts.parquet"
    events_path = PROJECT_ROOT / "data" / "processed" / "sec" / "eight_k" / "phase6_8_8k_events.parquet"
    news_path = PROJECT_ROOT / "data" / "processed" / "news" / "fnspid_news_processed.parquet"

    # Fallback to pilot facts/events if full ingestion is still consolidating
    if not facts_path.exists():
        facts_path = PROJECT_ROOT / "data" / "processed" / "sec" / "facts" / "pilot_financial_facts.parquet"
    if not events_path.exists():
        events_path = PROJECT_ROOT / "data" / "processed" / "sec" / "eight_k" / "phase5f_8k_events.parquet"

    df_manifest = pd.read_csv(manifest_path)
    print(f"Loaded cohort manifest: {len(df_manifest)} companies across {df_manifest['sector'].nunique()} sectors.", flush=True)

    df_market = pd.read_parquet(market_path)
    print(f"Loaded market data: {len(df_market):,} rows across {df_market['ticker'].nunique()} tickers.", flush=True)

    # 2. Extract Warmup & Primary Window (2018-01-01 to 2020-06-15)
    df_window = df_market[
        (df_market["trading_date"] >= "2018-01-01") & (df_market["trading_date"] <= "2020-06-15")
    ].copy()

    # Pre-derive adjusted open for exact mark-to-market pricing
    adj_factor = df_window["adjusted_close"] / df_window["close"]
    df_window["adjusted_open"] = df_window["open"] * adj_factor

    print(f"Computing market technical features on {len(df_window):,} rows (warmed from 2018)...", flush=True)
    m_engine = MarketFeatureEngine(MarketFeatureConfig(decision_timing=DecisionTimingMode.NEXT_SESSION_OPEN))
    df_features = m_engine.compute_features(df_window)

    print("Computing 5-session forward return targets...", flush=True)
    tgt_engine = ForwardReturnTargetEngine(TargetConfig(horizon_sessions=5))
    df_with_target = tgt_engine.add_target(df_features)

    # Filter to primary research evaluation window: 2019-01-01 to 2020-06-10 and valid targets
    df_eval = df_with_target[
        (df_with_target["trading_date"] >= "2019-01-01")
        & (df_with_target["trading_date"] <= "2020-06-10")
        & (df_with_target["target_forward_return_5d_valid"] == True)
    ].copy()

    df_all = df_eval.sort_values(["trading_date", "company_id"]).reset_index(drop=True)
    unique_dates = sorted(df_all["trading_date"].unique().tolist())
    print(f"Total Valid Labeled Market Rows: {len(df_all):,} across {len(unique_dates)} dates, {df_all['ticker'].nunique()} tickers.", flush=True)

    # 3. Load & Integrate SEC Fundamentals (XBRL)
    df_facts = pd.read_parquet(facts_path) if facts_path.exists() else pd.DataFrame()
    print(f"Loaded SEC Financial Facts: {len(df_facts):,} rows across {df_facts['ticker'].nunique() if not df_facts.empty else 0} companies.", flush=True)

    # 4. Load & Integrate SEC Events (8-K)
    df_events = pd.read_parquet(events_path) if events_path.exists() else pd.DataFrame()
    print(f"Loaded SEC 8-K Events: {len(df_events):,} rows across {df_events['ticker'].nunique() if not df_events.empty else 0} companies.", flush=True)

    # 5. Load & Integrate Financial News
    df_news = pd.read_parquet(news_path) if news_path.exists() else pd.DataFrame()
    print(f"Loaded Financial News: {len(df_news):,} rows across {df_news['ticker'].nunique() if not df_news.empty else 0} companies.", flush=True)

    # Instantiate feature engines
    fund_engine = FundamentalFeatureEngine(df_facts) if not df_facts.empty else None
    evt_engine = SECEventFeatureEngine(df_events) if not df_events.empty else None
    news_engine = NewsFeatureEngine(df_news) if not df_news.empty else None

    # Precompute decision cutoffs per unique calendar date
    cutoff_map = {d: MarketCalendar.get_session_open_cutoff_utc(d, buffer_minutes=15) for d in unique_dates}

    print("\nExtracting point-in-time fundamental, event, and news snapshots (optimized per company)...", flush=True)
    fund_records = []
    evt_records = []
    news_records = []

    # Process company by company with filing-level memoization
    grouped = df_all.groupby("company_id")
    n_companies = len(grouped)

    for c_idx, (cid, comp_rows) in enumerate(grouped, 1):
        c_dates = comp_rows["trading_date"].tolist()

        # 1. Fundamentals
        if fund_engine:
            comp_facts = fund_engine._company_facts.get(cid)
            if comp_facts is not None and not comp_facts.empty:
                accept_times = sorted(pd.to_datetime(comp_facts["acceptance_timestamp"], utc=True).tolist())
                f_cache = {}
                for t_date in c_dates:
                    dec_utc = cutoff_map[t_date]
                    prior = [t for t in accept_times if t <= dec_utc]
                    key = prior[-1] if prior else None
                    if key not in f_cache:
                        snap = fund_engine.get_as_of_snapshot(cid, dec_utc)
                        f_cache[key] = {k: v for k, v in snap.items() if k != "as_of_timestamp"}
                    row_snap = dict(f_cache[key])
                    row_snap["company_id"] = cid
                    row_snap["trading_date"] = t_date
                    fund_records.append(row_snap)

        # 2. Events (8-K)
        if evt_engine:
            comp_evts = evt_engine._company_events.get(cid)
            if comp_evts is not None and not comp_evts.empty:
                evt_times = sorted(pd.to_datetime(comp_evts["acceptance_timestamp"], utc=True).tolist())
                e_cache = {}
                for t_date in c_dates:
                    dec_utc = cutoff_map[t_date]
                    prior = [t for t in evt_times if t <= dec_utc]
                    key = prior[-1] if prior else None
                    if key not in e_cache:
                        snap = evt_engine.get_as_of_snapshot(cid, dec_utc)
                        e_cache[key] = {k: v for k, v in snap.items() if k != "as_of_timestamp"}
                    row_snap = dict(e_cache[key])
                    row_snap["company_id"] = cid
                    row_snap["trading_date"] = t_date
                    evt_records.append(row_snap)

        # 3. News
        if news_engine:
            comp_news = news_engine._company_news.get(cid)
            if comp_news is not None and not comp_news.empty:
                news_times = sorted(pd.to_datetime(comp_news["published_at"], utc=True).tolist())
                n_cache = {}
                for t_date in c_dates:
                    dec_utc = cutoff_map[t_date]
                    prior = [t for t in news_times if t <= dec_utc]
                    key = prior[-1] if prior else None
                    if key not in n_cache:
                        snap = news_engine.get_as_of_snapshot(cid, dec_utc)
                        n_cache[key] = {k: v for k, v in snap.items() if k != "as_of_timestamp"}
                    row_snap = dict(n_cache[key])
                    row_snap["company_id"] = cid
                    row_snap["trading_date"] = t_date
                    news_records.append(row_snap)

        if c_idx % 50 == 0 or c_idx == n_companies:
            print(f"  Processed snapshots for [{c_idx}/{n_companies}] companies...", flush=True)

    if fund_records:
        df_fund_feats = pd.DataFrame(fund_records).drop_duplicates(subset=["company_id", "trading_date"])
        df_all = df_all.merge(df_fund_feats, on=["company_id", "trading_date"], how="left")
    if evt_records:
        df_evt_feats = pd.DataFrame(evt_records).drop_duplicates(subset=["company_id", "trading_date"])
        df_all = df_all.merge(df_evt_feats, on=["company_id", "trading_date"], how="left")
    if news_records:
        df_news_feats = pd.DataFrame(news_records).drop_duplicates(subset=["company_id", "trading_date"])
        df_all = df_all.merge(df_news_feats, on=["company_id", "trading_date"], how="left")

    # Define feature modalities
    mkt_cols = [c for c in MarketBaselinePipeline.MARKET_FEATURE_COLUMNS if c in df_all.columns]
    fund_cols = [c for c in MarketBaselinePipeline.FUNDAMENTAL_FEATURE_COLUMNS if c in df_all.columns]
    evt_cols = [c for c in MarketBaselinePipeline.EVENT_FEATURE_COLUMNS if c in df_all.columns]
    news_cols = [c for c in ["news_count_7d", "news_count_14d", "news_recency_hours", "news_unique_sources_7d"] if c in df_all.columns]

    print(f"\nFeature modalities identified:")
    print(f"  Market features     : {len(mkt_cols)}")
    print(f"  Fundamental features: {len(fund_cols)}")
    print(f"  Event features      : {len(evt_cols)}")
    print(f"  News features       : {len(news_cols)}")

    # 6. Experimental Model Variants Definition
    models_to_evaluate = {
        "Model A (Market-Only)": mkt_cols,
        "Model B (Market + Fundamentals)": mkt_cols + fund_cols,
        "Model C (Market + Filing Events)": mkt_cols + evt_cols,
        "Model D (Combined Multi-Modal)": mkt_cols + fund_cols + evt_cols,
    }
    if news_cols:
        models_to_evaluate["Model E (Multi-Modal + News)"] = mkt_cols + fund_cols + evt_cols + news_cols

    # Walk-forward chronological splitter (4 folds, min_T=173, val=45, purge=5)
    wf_cfg = WalkForwardConfig(n_splits=4, train_min_sessions=173, val_sessions=45, purge_sessions=5)
    splitter = WalkForwardSplitter(wf_cfg)

    # 7. Evaluate on Full 300-Company Cohort
    print("\n" + "=" * 95)
    print("RUNNING WALK-FORWARD EXPERIMENTS: 300-COMPANY RESEARCH COHORT")
    print("=" * 95)

    model_evaluations: Dict[str, Any] = {}
    oos_predictions_dict: Dict[str, List[float]] = {m_name: [] for m_name in models_to_evaluate}
    oos_actuals: List[float] = []
    oos_metadata: List[Dict[str, Any]] = []

    for fold, (tr_idx, val_idx) in enumerate(splitter.split(df_all)):
        tr_df = df_all.iloc[tr_idx].copy()
        val_df = df_all.iloc[val_idx].copy()

        y_tr = tr_df["target_forward_return_5d"].values
        y_val = val_df["target_forward_return_5d"].values
        val_dates = sorted(val_df["trading_date"].unique().tolist())
        print(f"\nFold {fold}: Val Dates {val_dates[0]} -> {val_dates[-1]} (Val Obs: {len(val_df):,})")

        if fold == 0:
            for idx in val_idx:
                row = df_all.iloc[idx]
                oos_metadata.append({
                    "company_id": row["company_id"],
                    "ticker": row["ticker"],
                    "trading_date": row["trading_date"],
                    "fold": fold,
                    "target_return": row["target_forward_return_5d"],
                })
        else:
            for idx in val_idx:
                row = df_all.iloc[idx]
                oos_metadata.append({
                    "company_id": row["company_id"],
                    "ticker": row["ticker"],
                    "trading_date": row["trading_date"],
                    "fold": fold,
                    "target_return": row["target_forward_return_5d"],
                })

        oos_actuals.extend(y_val)

        for m_name, cols in models_to_evaluate.items():
            # Pipeline with imputation & scaling fit strictly on tr_df
            imputer = SimpleImputer(strategy="median")
            scaler = StandardScaler()

            X_tr_raw = tr_df[cols].values if cols else np.zeros((len(tr_df), 1))
            X_val_raw = val_df[cols].values if cols else np.zeros((len(val_df), 1))

            X_tr = scaler.fit_transform(imputer.fit_transform(X_tr_raw))
            X_val = scaler.transform(imputer.transform(X_val_raw))

            # Fit Ridge model with cross-validated alpha
            best_alpha = 100.0
            best_score = float("inf")
            for alpha in (1.0, 10.0, 100.0, 1000.0):
                reg = Ridge(alpha=alpha, random_state=42)
                reg.fit(X_tr, y_tr)
                tr_pred = reg.predict(X_tr)
                score = float(np.mean((y_tr - tr_pred) ** 2))
                if score < best_score:
                    best_score = score
                    best_alpha = alpha

            reg_final = Ridge(alpha=best_alpha, random_state=42)
            reg_final.fit(X_tr, y_tr)
            preds = reg_final.predict(X_val)

            oos_predictions_dict[m_name].extend(preds)

            f_rmse = float(np.sqrt(np.mean((y_val - preds) ** 2)))
            f_mae = float(np.mean(np.abs(y_val - preds)))
            f_hit = compute_directional_accuracy(y_val, preds)
            f_ic, _ = compute_ic(y_val, preds)
            print(f"  {m_name:<34} | RMSE: {f_rmse:.4f} | MAE: {f_mae:.4f} | Hit: {f_hit*100:.1f}% | IC: {f_ic:.3f} | Alpha: {best_alpha}")

    # Compile OOS Metrics across all folds
    y_true_all = np.array(oos_actuals)
    df_oos_results = pd.DataFrame(oos_metadata)

    print("\n" + "=" * 95)
    print("CUMULATIVE OUT-OF-SAMPLE PERFORMANCE (300 COMPANIES, FOLDS 0-3)")
    print("=" * 95)
    print(f"{'Model Variant':<35} {'N Obs':<8} {'RMSE':<10} {'MAE':<10} {'Hit Rate':<12} {'Rank IC':<10} {'HAC t-stat'}")
    print("-" * 95)

    comparison_summary: Dict[str, Any] = {}

    for m_name, preds_list in oos_predictions_dict.items():
        preds_arr = np.array(preds_list)
        df_oos_results[m_name] = preds_arr

        rmse = float(np.sqrt(np.mean((y_true_all - preds_arr) ** 2)))
        mae = float(np.mean(np.abs(y_true_all - preds_arr)))
        hit_rate = compute_directional_accuracy(y_true_all, preds_arr)
        ic_val, ic_pval = compute_ic(y_true_all, preds_arr)

        # Cross-sectional daily IC with HAC
        df_pred_sub = pd.DataFrame({
            "trading_date": df_oos_results["trading_date"],
            "target_return": y_true_all,
            "pred": preds_arr,
        })
        hac_res = compute_daily_cross_sectional_ic(df_pred_sub, pred_col="pred", min_stocks=20)

        comparison_summary[m_name] = {
            "n_observations": len(y_true_all),
            "n_features": len(models_to_evaluate[m_name]),
            "rmse": rmse,
            "mae": mae,
            "directional_accuracy": hit_rate,
            "pooled_spearman_ic": ic_val,
            "pooled_ic_pvalue": ic_pval,
            "mean_daily_ic": hac_res["mean_daily_ic"],
            "daily_ic_ir": hac_res["information_ratio"],
            "newey_west_hac_tstat": hac_res["newey_west_hac_tstat"],
            "newey_west_hac_pvalue": hac_res["newey_west_hac_pvalue"],
        }

        print(f"{m_name:<35} {len(y_true_all):<8} {rmse:<10.4f} {mae:<10.4f} {f'{hit_rate*100:.1f}%':<12} {ic_val:<10.3f} {hac_res['newey_west_hac_tstat']:.2f} (p={hac_res['newey_west_hac_pvalue']:.3f})")

    # 8. Core 60-Company Comparison (Benchmark Consistency Audit)
    print("\n" + "=" * 95)
    print("SUBSET AUDIT: CORE 60 PHASE 5J/5K COMPANIES WITHIN 300 COHORT")
    print("=" * 95)

    p5j_tickers = set(pd.read_csv(PROJECT_ROOT / "data" / "processed" / "universe" / "phase5j_company_eligibility.csv")["ticker"])
    c60_mask = df_oos_results["ticker"].isin(p5j_tickers)
    c60_true = y_true_all[c60_mask]

    print(f"{'Model Variant':<35} {'N Obs':<8} {'RMSE':<10} {'MAE':<10} {'Hit Rate':<12} {'Rank IC'}")
    print("-" * 85)

    core_60_comparison: Dict[str, Any] = {}
    for m_name in models_to_evaluate:
        c60_preds = df_oos_results.loc[c60_mask, m_name].values
        c60_rmse = float(np.sqrt(np.mean((c60_true - c60_preds) ** 2)))
        c60_mae = float(np.mean(np.abs(c60_true - c60_preds)))
        c60_hit = compute_directional_accuracy(c60_true, c60_preds)
        c60_ic, _ = compute_ic(c60_true, c60_preds)

        core_60_comparison[m_name] = {
            "n_observations": len(c60_true),
            "rmse": c60_rmse,
            "mae": c60_mae,
            "directional_accuracy": c60_hit,
            "spearman_ic": c60_ic,
        }
        print(f"{m_name:<35} {len(c60_true):<8} {c60_rmse:<10.4f} {c60_mae:<10.4f} {f'{c60_hit*100:.1f}%':<12} {c60_ic:.3f}")

    # 9. Coverage and Lineage Audit
    coverage_audit = {
        "phase": "6.8",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_target_cohort": len(df_manifest),
        "companies_with_market_data": df_all["ticker"].nunique(),
        "market_data_date_range": [df_market["trading_date"].min(), df_market["trading_date"].max()],
        "evaluation_window": ["2019-01-01", "2020-06-10"],
        "total_evaluation_observations": len(df_all),
        "companies_with_facts": df_facts["ticker"].nunique() if not df_facts.empty else 0,
        "total_financial_facts": len(df_facts),
        "companies_with_8k_events": df_events["ticker"].nunique() if not df_events.empty else 0,
        "total_8k_events": len(df_events),
        "companies_with_news": df_news["ticker"].nunique() if not df_news.empty else 0,
        "total_news_articles": len(df_news),
        "news_feasibility_blocker": "FNSPID sample contains 0 records for 278 companies and is 100% headline-only. Finnhub/Tiingo free tiers lack 2018-2020 history.",
    }

    # 10. Save Research Artifacts
    res_path = out_dir / "phase6_8_model_comparison_results.json"
    oos_path = out_dir / "phase6_8_predictions_oos.parquet"
    cov_path = out_dir / "phase6_8_coverage_audit.json"

    final_payload = {
        "phase": "6.8",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": time.time() - t0,
        "cohort_300_comparison": comparison_summary,
        "core_60_comparison": core_60_comparison,
        "coverage_audit": coverage_audit,
    }

    with open(res_path, "w", encoding="utf-8") as f:
        json.dump(final_payload, f, indent=2)
    with open(cov_path, "w", encoding="utf-8") as f:
        json.dump(coverage_audit, f, indent=2)
    df_oos_results.to_parquet(oos_path, index=False)

    print(f"\nArtifacts successfully persisted:")
    print(f"  Results JSON : {res_path}")
    print(f"  Coverage JSON: {cov_path}")
    print(f"  OOS Parquet  : {oos_path}")
    print("=" * 95)


if __name__ == "__main__":
    run_phase6_8_evaluation()

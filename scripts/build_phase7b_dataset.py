"""
Phase 7B — Historical Market-Panel Expansion and Dataset Builder.

Constructs the expanded research dataset across the 5-year modern period
(2019-01-01 to 2023-12-28, with 2018 used as warmup for technical indicators):
1. Market technical features:
   - 17 Original Market Baseline features (with dollar SMAs and duplicate momentum).
   - 15 Cleaned Market Features (stationary distance ratios, no dollar SMAs, no duplicates).
2. Point-in-time forward return targets:
   - Target A: Raw 5-session forward return (y_i).
   - Target B: Market-neutral excess forward return (y_i - y_mkt).
   - Target C: Sector-neutral excess forward return (y_i - y_sec).
3. Modality-separated fundamental features (2019-2021 development window).
4. Strictly non-destructive: saves to data/processed/research/phase7b/.
"""

import sys
import os
import json
import time
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Tuple
import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.features.market import MarketFeatureEngine, MarketFeatureConfig
from src.features.config import DecisionTimingMode
from src.features.target import ForwardReturnTargetEngine, TargetConfig
from src.features.fundamental import FundamentalFeatureEngine


def compute_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def build_phase7b_dataset():
    print("=" * 95)
    print("PHASE 7B: HISTORICAL MARKET-PANEL EXPANSION (2018-2023)")
    print("=" * 95)
    t0 = time.time()

    out_dir = PROJECT_ROOT / "data" / "processed" / "research" / "phase7b"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load authoritative inputs
    cohort_path = PROJECT_ROOT / "data" / "processed" / "universe" / "phase6_9a1_cohort_manifest.csv"
    market_path = PROJECT_ROOT / "data" / "processed" / "market" / "phase6_9a1_market_eligible.parquet"
    facts_path = PROJECT_ROOT / "data" / "processed" / "sec" / "phase6_9c" / "phase6_9c_financial_facts_consolidated_v2.parquet"

    print("Loading authoritative cohort and market data...")
    df_cohort = pd.read_csv(cohort_path)
    df_market = pd.read_parquet(market_path)
    print(f"  Cohort: {len(df_cohort)} companies, {df_cohort['sector'].nunique()} sectors.")
    print(f"  Market: {len(df_market):,} total historical rows.")

    # 2. Filter 2018-01-01 to 2023-12-28
    df_w = df_market[df_market["trading_date"] >= "2018-01-01"].copy()
    adj_factor = df_w["adjusted_close"] / df_w["close"]
    df_w["adjusted_open"] = df_w["open"] * adj_factor
    print(f"  Filtered window (>= 2018-01-01): {len(df_w):,} rows.")

    # 3. Market Feature Engineering
    print("\nComputing market technical features...")
    t_feat = time.time()
    m_engine = MarketFeatureEngine(MarketFeatureConfig(decision_timing=DecisionTimingMode.MARKET_CLOSE))
    df_feat = m_engine.compute_features(df_w)
    print(f"  Market features computed in {time.time() - t_feat:.1f}s. Shape: {df_feat.shape}")

    # 4. Target Generation (5-session horizon)
    print("\nComputing 5-session forward return targets...")
    t_tgt = time.time()
    tgt_engine = ForwardReturnTargetEngine(TargetConfig(horizon_sessions=5))
    df_tgt = tgt_engine.add_target(df_feat)
    print(f"  Target engineering completed in {time.time() - t_tgt:.1f}s. Shape: {df_tgt.shape}")

    # Filter to 2019-01-01 onwards (2018 served as 252-day warmup)
    df_panel = df_tgt[df_tgt["trading_date"] >= "2019-01-01"].copy()
    print(f"  Observations >= 2019-01-01: {len(df_panel):,} rows across {df_panel['trading_date'].nunique()} trading dates.")

    # Join sector from cohort
    df_panel = df_panel.merge(df_cohort[["ticker", "sector"]], on="ticker", how="left")
    assert df_panel["sector"].isna().sum() == 0, "Missing sector mappings!"

    # 5. Cleaned Feature Construction
    print("\nConstructing cleaned stationary market features...")
    df_panel["market_distance_sma20"] = (df_panel["close"] / df_panel["market_sma_20d"]) - 1.0
    df_panel["market_distance_sma50"] = (df_panel["close"] / df_panel["market_sma_50d"]) - 1.0
    df_panel["market_sma_ratio"] = (df_panel["market_sma_20d"] / df_panel["market_sma_50d"]) - 1.0

    # 6. Target Cross-Sectional Excess Return Construction
    print("Constructing Market-Neutral and Sector-Neutral targets...")
    valid_mask = df_panel["target_forward_return_5d_valid"] == True
    df_panel["target_raw"] = df_panel["target_forward_return_5d"]

    # Market-neutral excess return: y_i - daily_mkt_mean
    # Computed strictly per trading date on valid observations
    valid_df = df_panel[valid_mask].copy()
    mkt_mean = valid_df.groupby("trading_date")["target_raw"].transform("mean")
    sec_mean = valid_df.groupby(["trading_date", "sector"])["target_raw"].transform("mean")

    df_panel.loc[valid_mask, "target_mkt_excess"] = valid_df["target_raw"] - mkt_mean
    df_panel.loc[valid_mask, "target_sec_excess"] = valid_df["target_raw"] - sec_mean

    # Target variance statistics
    v_raw = float(np.var(df_panel.loc[valid_mask, "target_raw"]))
    v_mkt = float(np.var(df_panel.loc[valid_mask, "target_mkt_excess"]))
    v_sec = float(np.var(df_panel.loc[valid_mask, "target_sec_excess"]))

    print(f"  Target A (Raw Return) Variance           : {v_raw:.6f} (100.0%)")
    print(f"  Target B (Market-Neutral Excess) Variance: {v_mkt:.6f} ({v_mkt/v_raw*100:.1f}% of raw variance)")
    print(f"  Target C (Sector-Neutral Excess) Variance: {v_sec:.6f} ({v_sec/v_raw*100:.1f}% of raw variance)")

    # 7. Add Fundamental Features for 2019-2021 Development Period where available
    print("\nExtracting point-in-time fundamental snapshots for development comparison...")
    t_fund = time.time()
    df_facts = pd.read_parquet(facts_path)
    fund_engine = FundamentalFeatureEngine(df_facts)

    # We compute fundamental features using point-in-time as-of snapshot for unique dates
    unique_dates = sorted(df_panel["trading_date"].unique().tolist())
    date_to_utc = {d: pd.to_datetime(d + " 16:00:00", utc=True) for d in unique_dates}

    fund_records = []
    unique_cids = df_panel["company_id"].unique().tolist()
    
    # Accelerated cached snapshot extraction
    for cid in unique_cids:
        c_sub = df_panel[df_panel["company_id"] == cid]
        c_dates = c_sub["trading_date"].tolist()
        comp_facts = fund_engine._company_facts.get(cid)
        f_cache = {}

        if comp_facts is not None and not comp_facts.empty:
            accept_times = sorted(pd.to_datetime(comp_facts["acceptance_timestamp"], utc=True).tolist())
            for t_date in c_dates:
                dec_utc = date_to_utc[t_date]
                prior = [t for t in accept_times if t <= dec_utc]
                key = prior[-1] if prior else None
                if key not in f_cache:
                    snap = fund_engine.get_as_of_snapshot(cid, dec_utc)
                    f_cache[key] = {
                        "fundamental_diluted_eps": snap.get("fundamental_diluted_eps", np.nan),
                        "fundamental_ratio_net_margin": snap.get("fundamental_ratio_net_margin", np.nan),
                        "fundamental_ratio_roa": snap.get("fundamental_ratio_roa", np.nan),
                        "fundamental_ratio_debt_to_assets": snap.get("fundamental_ratio_debt_to_assets", np.nan),
                        "fundamental_ratio_debt_to_equity": snap.get("fundamental_ratio_debt_to_equity", np.nan),
                        "fundamental_ratio_ocf_to_net_income": snap.get("fundamental_ratio_ocf_to_net_income", np.nan),
                        "fundamental_revenue_age_days": snap.get("fundamental_revenue_age_days", np.nan),
                    }
                row_snap = dict(f_cache[key])
                row_snap["company_id"] = cid
                row_snap["trading_date"] = t_date
                fund_records.append(row_snap)
        else:
            for t_date in c_dates:
                fund_records.append({
                    "company_id": cid,
                    "trading_date": t_date,
                    "fundamental_diluted_eps": np.nan,
                    "fundamental_ratio_net_margin": np.nan,
                    "fundamental_ratio_roa": np.nan,
                    "fundamental_ratio_debt_to_assets": np.nan,
                    "fundamental_ratio_debt_to_equity": np.nan,
                    "fundamental_ratio_ocf_to_net_income": np.nan,
                    "fundamental_revenue_age_days": np.nan,
                })

    df_fund = pd.DataFrame(fund_records)
    print(f"  Fundamental extraction done in {time.time() - t_fund:.1f}s ({len(df_fund):,} records).")

    # Merge fundamentals into panel
    df_panel = df_panel.merge(df_fund, on=["company_id", "trading_date"], how="left")

    # Construct cleaned fundamental features
    df_panel["fundamental_earnings_yield"] = (df_panel["fundamental_diluted_eps"] / df_panel["close"]).clip(-0.5, 0.5)
    df_panel["fundamental_net_margin_cl"] = df_panel["fundamental_ratio_net_margin"].clip(-2.0, 2.0)
    df_panel["fundamental_roa_cl"] = df_panel["fundamental_ratio_roa"].clip(-1.0, 1.0)
    df_panel["fundamental_debt_to_assets_cl"] = df_panel["fundamental_ratio_debt_to_assets"].clip(0.0, 5.0)
    df_panel["fundamental_debt_to_equity_cl"] = df_panel["fundamental_ratio_debt_to_equity"].clip(-5.0, 10.0)
    df_panel["fundamental_ocf_to_ni_cl"] = df_panel["fundamental_ratio_ocf_to_net_income"].clip(-10.0, 10.0)

    # 8. Save Dataset
    dataset_out_path = out_dir / "phase7b_market_expanded_dataset.parquet"
    print(f"\nSaving expanded panel to {dataset_out_path}...")
    df_panel.to_parquet(dataset_out_path, index=False)
    file_size = os.path.getsize(dataset_out_path)
    file_sha = compute_sha256(dataset_out_path)
    print(f"Saved {len(df_panel):,} rows, {file_size:,} bytes. SHA-256: {file_sha}")

    # 9. Create Reproducible Manifest
    manifest = {
        "phase": "Phase 7B",
        "created_at_utc": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "dataset_path": str(dataset_out_path.relative_to(PROJECT_ROOT)),
        "dataset_sha256": file_sha,
        "dataset_size_bytes": file_size,
        "total_rows": len(df_panel),
        "valid_target_rows": int(valid_mask.sum()),
        "unique_trading_dates": int(df_panel["trading_date"].nunique()),
        "date_range_start": str(df_panel["trading_date"].min()),
        "date_range_end": str(df_panel["trading_date"].max()),
        "unique_tickers": int(df_panel["ticker"].nunique()),
        "unique_companies": int(df_panel["company_id"].nunique()),
        "source_cohort_manifest": str(cohort_path.relative_to(PROJECT_ROOT)),
        "source_cohort_sha256": compute_sha256(cohort_path),
        "source_market_data": str(market_path.relative_to(PROJECT_ROOT)),
        "source_market_sha256": compute_sha256(market_path),
        "source_sec_facts": str(facts_path.relative_to(PROJECT_ROOT)),
        "source_sec_facts_sha256": compute_sha256(facts_path),
        "target_definitions": {
            "target_raw": "Forward 5-session arithmetic return: (P_{T+5, close}^adj - P_{T+1, open}^adj) / P_{T+1, open}^adj",
            "target_mkt_excess": "Market-neutral excess return: y_i - daily_mkt_mean",
            "target_sec_excess": "Sector-neutral excess return: y_i - daily_sec_mean",
        },
        "target_variances": {
            "var_raw": v_raw,
            "var_mkt": v_mkt,
            "var_sec": v_sec,
            "pct_mkt_var_of_raw": v_mkt / v_raw * 100.0,
            "pct_sec_var_of_raw": v_sec / v_raw * 100.0,
        },
        "observations_per_year": {
            y: {
                "total_rows": int(len(df_panel[df_panel["trading_date"].str[:4] == str(y)])),
                "valid_targets": int((df_panel[df_panel["trading_date"].str[:4] == str(y)]["target_forward_return_5d_valid"] == True).sum()),
                "tickers": int(df_panel[df_panel["trading_date"].str[:4] == str(y)]["ticker"].nunique()),
                "sessions": int(df_panel[df_panel["trading_date"].str[:4] == str(y)]["trading_date"].nunique()),
            }
            for y in range(2019, 2024)
        }
    }

    manifest_out_path = out_dir / "phase7b_dataset_manifest.json"
    with open(manifest_out_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"Saved manifest to {manifest_out_path}.")
    print(f"Total time elapsed: {time.time() - t0:.1f}s.")
    return df_panel, manifest


if __name__ == "__main__":
    build_phase7b_dataset()

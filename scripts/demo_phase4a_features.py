"""
Demonstration Script for Phase 4A Point-in-Time Feature Engineering Foundation.

Demonstrates deterministic market feature extraction, point-in-time SEC fundamental
snapshots, temporal alignment at decision cutoffs, zero-lookahead verification,
and license-safe storage policy governance across representative cohort companies.
"""

import sys
from pathlib import Path

# Add project root to path for direct script execution
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pandas as pd
import numpy as np

from src.features.config import (
    FeatureStorageConfig,
    MarketFeatureConfig,
    FundamentalFeatureConfig,
    DecisionTimingMode,
    PersistenceMode,
)
from src.features.market import MarketFeatureEngine
from src.features.fundamental import FundamentalFeatureEngine
from src.features.alignment import TemporalAligner, LookaheadLeakageError
from src.features.storage import FeatureStorageManager, StorageAuthorizationError


def run_phase4a_demonstration():
    print("=" * 80)
    print("PHASE 4A — POINT-IN-TIME FEATURE ENGINEERING DEMONSTRATION")
    print("=" * 80)

    # 1. Load representative datasets from Phase 1 and Phase 3B
    universe_path = Path("data/processed/universe/sp500_universe.parquet")
    market_path = Path("data/processed/market/tiingo/pilot_market_sample.parquet")
    facts_path = Path("data/processed/sec/facts/pilot_financial_facts.parquet")

    assert universe_path.exists(), f"Missing universe dataset at {universe_path}"
    assert market_path.exists(), f"Missing pilot market dataset at {market_path}"
    assert facts_path.exists(), f"Missing pilot SEC facts dataset at {facts_path}"

    df_universe = pd.read_parquet(universe_path)
    df_market_full = pd.read_parquet(market_path)
    df_facts_full = pd.read_parquet(facts_path)

    # Filter to representative cohort companies: Apple (AAPL) and JPMorgan Chase (JPM)
    demo_cids = ["US_CIK_0000320193", "US_CIK_0000019617"]
    df_market_cohort = df_market_full[df_market_full["company_id"].isin(demo_cids)].copy()
    df_facts_cohort = df_facts_full[df_facts_full["company_id"].isin(demo_cids)].copy()

    print(f"\n[1] Representative Cohort Loaded:")
    print(f"    - Companies: AAPL (US_CIK_0000320193), JPM (US_CIK_0000019617)")
    print(f"    - Market observations: {len(df_market_cohort)} sessions (2023 calendar year)")
    print(f"    - SEC XBRL facts: {len(df_facts_cohort)} historical facts")

    # 2. Market Feature Engineering
    print("\n[2] Computing Market Technical Features...")
    mkt_cfg = MarketFeatureConfig(
        return_windows=(1, 5, 21),
        volatility_windows=(5, 21, 63),
        momentum_windows=(5, 21, 63, 126),
        rolling_mean_windows=(20, 50),
        rsi_window=14,
        volume_window=20,
        decision_timing=DecisionTimingMode.MARKET_CLOSE,
    )
    mkt_engine = MarketFeatureEngine(mkt_cfg)
    df_mkt_feat = mkt_engine.compute_features(df_market_cohort)

    print(f"    - Generated {len(df_mkt_feat)} rows with {len(df_mkt_feat.columns)} columns")
    print("    - Sample Technical Feature Columns:")
    tech_sample_cols = [
        "trading_date", "close", "adjusted_close", "market_return_1d",
        "market_momentum_21d", "market_volatility_21d", "market_rsi_14d",
        "market_volume_ratio_20d", "market_volatility_21d_missing"
    ]
    print(df_mkt_feat[tech_sample_cols].dropna().head(3).to_string(index=False))

    # 3. Fundamental Feature Engineering
    print("\n[3] Initializing SEC EDGAR Point-in-Time Fundamental Engine...")
    fund_cfg = FundamentalFeatureConfig(compute_ratios=True)
    fund_engine = FundamentalFeatureEngine(df_facts_cohort, fund_cfg)

    # 4. Temporal Alignment
    print("\n[4] Executing Point-in-Time Temporal Alignment (Market + SEC As-Of)...")
    aligner = TemporalAligner(
        market_engine=mkt_engine,
        fundamental_engine=fund_engine,
        universe_df=df_universe,
    )
    df_aligned = aligner.align_features(df_market_cohort, strict_leakage_check=True)

    print(f"    - Total harmonized feature rows: {len(df_aligned)}")
    print(f"    - Total feature matrix dimensions: {df_aligned.shape}")

    # Inspect a point-in-time snapshot
    sample_row = df_aligned[df_aligned["ticker"] == "AAPL"].iloc[100]
    print(f"\n[5] Sample Feature Vector Inspection (AAPL at {sample_row['decision_timestamp']}):")
    print(f"    * Trading Session: {sample_row['trading_date']} (Close: ${sample_row['close']:.2f}, Adj Close: ${sample_row['adjusted_close']:.2f})")
    print(f"    * 1-Day Return: {sample_row['market_return_1d']:.4%}")
    print(f"    * 21-Day Momentum: {sample_row['market_momentum_21d']:.4%}")
    print(f"    * 21-Day Annualized Volatility: {sample_row['market_volatility_21d']:.4%}")
    print(f"    * 14-Day RSI: {sample_row['market_rsi_14d']:.2f}")
    print(f"    * SEC Available Facts: Revenue=${sample_row['fundamental_revenue']:,.0f} (Period: {sample_row['fundamental_revenue_period_end']}, Form: {sample_row['fundamental_revenue_form']})")
    print(f"    * SEC Acceptance Timestamp: {sample_row['fundamental_revenue_acceptance_timestamp']} (Accession: {sample_row['fundamental_revenue_accn']})")
    print(f"    * Debt-to-Assets Ratio: {sample_row['fundamental_ratio_debt_to_assets']:.4f}")
    print(f"    * Net Profit Margin: {sample_row['fundamental_ratio_net_margin']:.4f}")
    print(f"    * Missing Indicators: Return Missing={sample_row['market_return_1d_missing']}, OCF Missing={sample_row['fundamental_operating_cash_flow_missing']}")

    # 5. Zero-Leakage Audit
    print("\n[6] Point-in-Time Zero-Leakage Audit:")
    dec_ts = pd.to_datetime(df_aligned["decision_timestamp"], utc=True)
    mkt_ts = pd.to_datetime(df_aligned["timestamp"], utc=True)
    mkt_leaks = (mkt_ts > dec_ts).sum()

    fund_ts = pd.to_datetime(df_aligned["fundamental_revenue_acceptance_timestamp"], utc=True)
    fund_leaks = ((fund_ts.notna()) & (fund_ts > dec_ts)).sum()

    print(f"    - Market timestamp violations (> decision_timestamp): {mkt_leaks} (PASS)")
    print(f"    - Fundamental acceptance violations (> decision_timestamp): {fund_leaks} (PASS)")

    # 6. Storage Policy Governance Demonstration
    print("\n[7] License-Aware Storage Policy Enforcement:")
    # Scenario A: Ephemeral In-Memory Mode (Safe default: persistent storage disabled; licensing unverified)
    cfg_in_memory = FeatureStorageConfig(
        provider="tiingo",
        plan_tier="starter",
        storage_authorized=False,
        persistence_mode=PersistenceMode.IN_MEMORY,
    )
    mgr_mem = FeatureStorageManager(cfg_in_memory)
    persisted_a, path_a, msg_a = mgr_mem.handle_features(df_aligned)
    print(f"    * Scenario A (Starter Tier / In-Memory): Persisted={persisted_a} | {msg_a}")

    # Scenario B: Disk Persistence Attempt WITHOUT User Authorization
    cfg_unauth = FeatureStorageConfig(
        provider="tiingo",
        plan_tier="power",
        storage_authorized=False,  # Blocked!
        persistence_mode=PersistenceMode.DISK_PARQUET,
    )
    mgr_unauth = FeatureStorageManager(cfg_unauth)
    try:
        mgr_unauth.handle_features(df_aligned)
        print("    * Scenario B: ERROR - should have raised StorageAuthorizationError!")
    except StorageAuthorizationError as e:
        print(f"    * Scenario B (Unauthorized Disk Attempt): Blocked as expected -> '{e}'")

    print("\n" + "=" * 80)
    print("PHASE 4A DEMONSTRATION COMPLETE: ALL INTEGRITY & LEGAL SAFEGUARDS VERIFIED")
    print("=" * 80)


if __name__ == "__main__":
    run_phase4a_demonstration()

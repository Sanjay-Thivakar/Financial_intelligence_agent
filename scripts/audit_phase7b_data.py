import os
import glob
import hashlib
import json
import pandas as pd
import numpy as np

def run_audit():
    print("===============================================================")
    print("PHASE 7B-A: DATA-READINESS AND COVERAGE AUDIT")
    print("===============================================================")
    
    # 1. Cohort manifest
    cohort_path = "data/processed/universe/phase6_9a1_cohort_manifest.csv"
    if os.path.exists(cohort_path):
        df_cohort = pd.read_csv(cohort_path)
        print(f"1. Cohort Manifest:")
        print(f"   Rows: {len(df_cohort)}, Columns: {df_cohort.columns.tolist()}")
        print(f"   Unique Tickers: {df_cohort['ticker'].nunique()}, Unique CIKs: {df_cohort['cik'].nunique()}")
        sector_col = 'gics_sector' if 'gics_sector' in df_cohort.columns else ('sector' if 'sector' in df_cohort.columns else None)
        if sector_col:
            print(f"   Sector counts ({sector_col}): {df_cohort[sector_col].value_counts().to_dict()}")
        cohort_tickers = set(df_cohort['ticker'].str.upper().tolist())
    else:
        print("1. Cohort Manifest NOT FOUND")
        cohort_tickers = set()

    # 2. Market eligible parquet
    market_path = "data/processed/market/phase6_9a1_market_eligible.parquet"
    if os.path.exists(market_path):
        df_mkt = pd.read_parquet(market_path)
        print(f"\n2. Market Eligible Dataset:")
        print(f"   Rows: {len(df_mkt):,}, Columns: {df_mkt.columns.tolist()}")
        print(f"   Unique tickers: {df_mkt['ticker'].nunique()}")
        date_col = 'trading_date' if 'trading_date' in df_mkt.columns else 'date'
        adj_close_col = 'adjusted_close' if 'adjusted_close' in df_mkt.columns else 'adj_close'
        df_mkt['date'] = pd.to_datetime(df_mkt[date_col])
        min_date, max_date = df_mkt['date'].min(), df_mkt['date'].max()
        print(f"   Full Date range: {min_date.strftime('%Y-%m-%d')} to {max_date.strftime('%Y-%m-%d')}")
        print(f"   Total unique trading dates: {df_mkt['date'].nunique()}")
        
        # Check coverage for 2019 - 2023
        df_mkt_recent = df_mkt[df_mkt['date'] >= '2019-01-01'].copy()
        print(f"   Observations >= 2019-01-01: {len(df_mkt_recent):,}")
        dates_recent = df_mkt_recent['date'].nunique()
        print(f"   Unique trading days >= 2019-01-01: {dates_recent}")
        per_ticker = df_mkt_recent.groupby('ticker')['date'].count()
        print(f"   Per-ticker session count: min={per_ticker.min()}, median={per_ticker.median()}, max={per_ticker.max()}")
        incomplete_tickers = per_ticker[per_ticker < dates_recent]
        print(f"   Tickers with < {dates_recent} sessions: {len(incomplete_tickers)} -> {incomplete_tickers.to_dict()}")
        
        # Check volume and price validity
        zero_vol = (df_mkt_recent['volume'] <= 0).sum()
        neg_price = (df_mkt_recent['close'] <= 0).sum()
        chk_cols = [c for c in ['open', 'high', 'low', 'close', adj_close_col, 'volume'] if c in df_mkt_recent.columns]
        nan_mkt = df_mkt_recent[chk_cols].isna().sum().to_dict()
        print(f"   Zero/neg volume rows: {zero_vol}, Non-positive close rows: {neg_price}")
        print(f"   NaN values in OHLCV: {nan_mkt}")
        
        # Duplicate check
        dups = df_mkt_recent.duplicated(subset=['ticker', 'date']).sum()
        print(f"   Duplicate (ticker, date) pairs: {dups}")
        
        # Yearly distribution
        df_mkt_recent['year'] = df_mkt_recent['date'].dt.year
        print("   Observations per year:")
        for y, count in df_mkt_recent['year'].value_counts().sort_index().items():
            n_dates = df_mkt_recent[df_mkt_recent['year'] == y]['date'].nunique()
            print(f"     Year {y}: {count:,} rows across {n_dates} trading sessions")
            
    # 3. SEC Financial Facts Consolidated
    sec_facts_path = "data/processed/sec/phase6_9c/phase6_9c_financial_facts_consolidated_v2.parquet"
    if os.path.exists(sec_facts_path):
        df_sec = pd.read_parquet(sec_facts_path)
        print(f"\n3. SEC Financial Facts Consolidated v2:")
        print(f"   Rows: {len(df_sec):,}, Columns: {df_sec.columns.tolist()}")
        if 'cik' in df_sec.columns:
            print(f"   Unique CIKs: {df_sec['cik'].nunique()}")
        if 'ticker' in df_sec.columns:
            print(f"   Unique Tickers: {df_sec['ticker'].nunique()}")
        acc_col = 'acceptance_timestamp' if 'acceptance_timestamp' in df_sec.columns else ('acceptance_datetime' if 'acceptance_datetime' in df_sec.columns else None)
        if acc_col:
            df_sec['acc_dt'] = pd.to_datetime(df_sec[acc_col])
            print(f"   Acceptance timestamp range: {df_sec['acc_dt'].min()} to {df_sec['acc_dt'].max()}")
        filed_col = 'filed_date' if 'filed_date' in df_sec.columns else ('filing_date' if 'filing_date' in df_sec.columns else None)
        if filed_col:
            df_sec['f_dt'] = pd.to_datetime(df_sec[filed_col])
            print(f"   Filed date range: {df_sec['f_dt'].min()} to {df_sec['f_dt'].max()}")
            facts_by_year = df_sec['f_dt'].dt.year.value_counts().sort_index()
            print(f"   Facts by filed year: {facts_by_year.to_dict()}")
        
    # 4. SEC 8-K Events Consolidated
    sec_8k_path = "data/processed/sec/phase6_9c/phase6_9c_8k_events_consolidated_v2.parquet"
    if os.path.exists(sec_8k_path):
        df_8k = pd.read_parquet(sec_8k_path)
        print(f"\n4. SEC 8-K Events Consolidated v2:")
        print(f"   Rows: {len(df_8k):,}, Columns: {df_8k.columns.tolist()}")
        if 'cik' in df_8k.columns:
            print(f"   Unique CIKs: {df_8k['cik'].nunique()}")
        acc_col_8k = 'acceptance_timestamp' if 'acceptance_timestamp' in df_8k.columns else ('acceptance_datetime' if 'acceptance_datetime' in df_8k.columns else None)
        if acc_col_8k:
            df_8k['acc_dt'] = pd.to_datetime(df_8k[acc_col_8k])
            print(f"   Acceptance timestamp range: {df_8k['acc_dt'].min()} to {df_8k['acc_dt'].max()}")
        filed_col_8k = 'filed_date' if 'filed_date' in df_8k.columns else ('filing_date' if 'filing_date' in df_8k.columns else None)
        if filed_col_8k:
            df_8k['f_dt'] = pd.to_datetime(df_8k[filed_col_8k])
            print(f"   Filed date range: {df_8k['f_dt'].min()} to {df_8k['f_dt'].max()}")
            events_by_year = df_8k['f_dt'].dt.year.value_counts().sort_index()
            print(f"   8-K events by filed year: {events_by_year.to_dict()}")

    # 5. Raw SEC Caches
    print("\n5. Raw SEC Caches:")
    raw_sec_files = glob.glob("data/raw/sec/**/*", recursive=True)
    raw_sec_files = [f for f in raw_sec_files if os.path.isfile(f)]
    print(f"   Total raw SEC cache files: {len(raw_sec_files)}")
    if raw_sec_files:
        print(f"   Sample paths: {raw_sec_files[:5]}")
        
    # 6. Check Phase 6.9D and 7A research datasets
    print("\n6. Existing Research Datasets:")
    for path in [
        "data/processed/research/phase6_9d/multimodal_features_df.parquet",
        "data/processed/research/phase7a/phase7a_predictions_oos.parquet",
        "data/processed/research/phase7a/phase7a_experiment_results.json"
    ]:
        if os.path.exists(path):
            size = os.path.getsize(path)
            print(f"   {path}: exists, {size:,} bytes")
        else:
            print(f"   {path}: MISSING")

if __name__ == "__main__":
    run_audit()

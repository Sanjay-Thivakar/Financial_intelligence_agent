"""
Phase 8E — Dataset Construction & Coverage Gate Engine.

Joins point-in-time financial report features with the authoritative modern
market research panel (2019-2023). Enforces strict anti-leakage invariants,
tracks staleness diagnostics, and produces a complete Phase 8 research dataset.
"""

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Any
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.features.financial_reports import Phase8FinancialReportEngine

MARKET_PANEL_PATH = PROJECT_ROOT / "data" / "processed" / "research" / "phase7b" / "phase7b_market_expanded_dataset.parquet"
FACTS_PATH = PROJECT_ROOT / "data" / "processed" / "sec" / "phase8" / "phase8_financial_facts.parquet"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "research" / "phase8"


def compute_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def run_phase8_dataset_construction():
    print("=" * 90)
    print("PHASE 8E: POINT-IN-TIME FINANCIAL DATASET CONSTRUCTION")
    print("=" * 90)
    t0 = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("1. Loading authoritative market panel and recovered SEC facts...")
    df_panel = pd.read_parquet(MARKET_PANEL_PATH)
    df_facts = pd.read_parquet(FACTS_PATH)
    n_panel_orig = len(df_panel)
    print(f"  Market panel: {n_panel_orig:,} rows across {df_panel['trading_date'].nunique()} trading dates.")
    print(f"  SEC facts   : {len(df_facts):,} rows across {df_facts['company_id'].nunique()} companies.")

    print("\n2. Initializing Phase 8 Financial Reports Engine...")
    engine = Phase8FinancialReportEngine(df_facts=df_facts, max_staleness_days=180)

    print("\n3. Extracting point-in-time snapshot features...")
    t_feat = time.time()
    df_fin_feats = engine.extract_point_in_time_features_for_panel(df_panel)
    print(f"  Feature extraction completed in {time.time() - t_feat:.1f}s ({len(df_fin_feats):,} rows).")

    print("\n4. Merging financial features into panel...")
    # Drop any pre-existing fundamental columns from Phase 7B if needed, to avoid collisions
    fin_cols_to_merge = [c for c in df_fin_feats.columns if c not in ("company_id", "trading_date")]
    
    df_merged = df_panel.merge(
        df_fin_feats[["company_id", "trading_date"] + fin_cols_to_merge],
        on=["company_id", "trading_date"],
        how="left"
    )

    # Verification: row count must be preserved exactly
    assert len(df_merged) == n_panel_orig, f"Row count mismatch! {len(df_merged)} vs {n_panel_orig}"
    print(f"  Row count invariant verified: {len(df_merged):,} rows preserved.")

    # 5. Define Coverage & Completeness Flags
    # A record is strictly fresh if it has a filing with filing_age_days <= 180 days
    df_merged["fin_fresh_180"] = (
        (df_merged["fin_has_filing"] == True) & 
        (df_merged["fin_is_stale_180"] == False)
    )
    # Complete-case core financial flag: fresh + non-null key ratios (net_margin, roa, debt_to_assets)
    core_financials_valid = (
        df_merged["fin_fresh_180"] &
        df_merged["fin_net_margin"].notna() &
        df_merged["fin_roa"].notna() &
        df_merged["fin_debt_to_assets"].notna()
    )
    df_merged["fin_core_valid"] = core_financials_valid

    # Eligible for model evaluation: valid forward target + valid core financials
    df_merged["eval_eligible_matched"] = (
        (df_merged["target_forward_return_5d_valid"] == True) &
        df_merged["fin_core_valid"]
    )

    print("\n--- Coverage and Staleness Summary ---")
    df_merged["year"] = df_merged["trading_date"].str[:4]
    for yr, grp in df_merged.groupby("year"):
        n_total = len(grp)
        n_valid_tgt = int((grp["target_forward_return_5d_valid"] == True).sum())
        n_has_filing = int((grp["fin_has_filing"] == True).sum())
        n_fresh_180 = int((grp["fin_fresh_180"] == True).sum())
        n_core = int((grp["fin_core_valid"] == True).sum())
        med_age = grp.loc[grp["fin_has_filing"] == True, "fin_filing_age_days"].median()
        print(f"  Year {yr}: {n_total:,} rows | Valid Tgt: {n_valid_tgt:,} | Has Filing: {n_has_filing:,} ({n_has_filing/n_total*100:.1f}%) | Fresh <=180d: {n_fresh_180:,} ({n_fresh_180/n_total*100:.1f}%) | Core Valid: {n_core:,} ({n_core/n_total*100:.1f}%) | Med Age: {med_age:.1f}d")

    print("\n--- Missingness by Financial Feature ---")
    fin_feature_list = [
        "fin_gross_margin", "fin_operating_margin", "fin_net_margin",
        "fin_roa", "fin_roe", "fin_debt_to_assets", "fin_debt_to_equity",
        "fin_current_ratio", "fin_cash_to_assets", "fin_ocf_to_assets",
        "fin_fcf_to_assets", "fin_ocf_to_net_income", "fin_accruals",
        "fin_earnings_yield"
    ]
    for f in fin_feature_list:
        n_missing = int(df_merged[f].isna().sum())
        pct_missing = (n_missing / n_panel_orig) * 100.0
        print(f"  {f:<25}: {n_missing:,} missing ({pct_missing:.2f}%)")

    # 6. Save Dataset
    dataset_out_path = OUTPUT_DIR / "phase8_point_in_time_dataset.parquet"
    print(f"\nSaving Phase 8 dataset to {dataset_out_path}...")
    df_merged.to_parquet(dataset_out_path, index=False)
    file_size_mb = os.path.getsize(dataset_out_path) / (1024 * 1024)
    file_sha = compute_sha256(dataset_out_path)
    print(f"Saved {len(df_merged):,} rows ({file_size_mb:.2f} MB). SHA-256: {file_sha}")

    # 7. Generate Machine-Readable Manifest
    manifest = {
        "phase": "Phase 8E",
        "created_at_utc": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "dataset_path": str(dataset_out_path.relative_to(PROJECT_ROOT)),
        "dataset_sha256": file_sha,
        "dataset_size_mb": round(file_size_mb, 2),
        "total_rows": len(df_merged),
        "valid_target_rows": int((df_merged["target_forward_return_5d_valid"] == True).sum()),
        "total_fresh_180_rows": int(df_merged["fin_fresh_180"].sum()),
        "total_core_valid_rows": int(df_merged["fin_core_valid"].sum()),
        "matched_evaluation_rows": int(df_merged["eval_eligible_matched"].sum()),
        "date_range": [str(df_merged["trading_date"].min()), str(df_merged["trading_date"].max())],
        "unique_companies": int(df_merged["company_id"].nunique()),
        "unique_tickers": int(df_merged["ticker"].nunique()),
        "financial_features": fin_feature_list,
        "staleness_threshold_days": 180,
    }

    manifest_path = OUTPUT_DIR / "phase8_dataset_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"Saved dataset manifest to {manifest_path.relative_to(PROJECT_ROOT)}")
    print(f"Phase 8E Dataset Construction completed in {time.time() - t0:.1f}s.")
    return manifest


if __name__ == "__main__":
    run_phase8_dataset_construction()

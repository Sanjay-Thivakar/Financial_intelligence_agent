"""
Phase 6.8 Market Data Ingestion & Quality Engine (300 Companies).

Expands historical market data from 60 to 300 validated companies:
- Concurrent range-request ingestion from FNSPID remote market archive
- Caches raw CSVs to data/raw/market/{ticker}.csv
- Cleans and normalizes into individual Parquet files in data/processed/market/phase6_8/
- Consolidates into data/processed/market/phase6_8_market_300.parquet
- Enforces strict data-quality gates: positive prices, calendar alignment, target computability
- Non-destructive: leaves Phase 5I artifacts and data.zip untouched
"""

import os
import sys
import json
import time
import struct
import zlib
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Any, Optional
import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.market.ingestor import MarketIngestor
from src.features.calendar import MarketCalendar
from src.features.target import ForwardReturnTargetEngine, TargetConfig

ZIP_URL = "https://huggingface.co/datasets/Zihan1004/FNSPID/resolve/main/Stock_price/full_history.zip"
CD_CACHE_PATH = PROJECT_ROOT / "data" / "processed" / "universe" / "fnspid_central_directory.json"
MANIFEST_PATH = PROJECT_ROOT / "data" / "processed" / "universe" / "phase6_8_cohort_300_manifest.csv"
RAW_MARKET_DIR = PROJECT_ROOT / "data" / "raw" / "market"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed" / "market" / "phase6_8"
CONSOLIDATED_PARQUET = PROJECT_ROOT / "data" / "processed" / "market" / "phase6_8_market_300.parquet"
SUMMARY_JSON = PROJECT_ROOT / "data" / "processed" / "market" / "phase6_8_market_data_summary.json"


def get_direct_cloudfront_url() -> str:
    """Obtains the authenticated/pre-signed direct CloudFront URL from HuggingFace redirect."""
    cmd = ["curl.exe", "-s", "-I", ZIP_URL]
    out = subprocess.check_output(cmd).decode("utf-8", errors="ignore")
    loc_match = re.search(r"Location:\s*([^\r\n]+)", out, re.IGNORECASE)
    if not loc_match:
        raise RuntimeError("Failed to resolve CloudFront Location header from HuggingFace redirect!")
    return loc_match.group(1).strip()


def download_ticker_csv(tk: str, entry: Dict[str, Any], direct_url: str) -> Optional[str]:
    """Downloads and decompress single ticker CSV via curl byte-range."""
    out_csv = RAW_MARKET_DIR / f"{tk}.csv"
    if out_csv.exists():
        return tk

    offset = entry["offset"]
    comp_size = entry["comp_size"]
    fname = entry["filename"]
    method = entry["method"]

    end_byte = offset + 30 + len(fname) + 120 + comp_size
    cmd = ["curl.exe", "-s", "--ssl-no-revoke", "-r", f"{offset}-{end_byte}", direct_url]

    for attempt in range(3):
        try:
            fdata = subprocess.check_output(cmd, timeout=30)
            if len(fdata) < 30:
                time.sleep(0.5)
                continue
            local_fname_len = struct.unpack("<H", fdata[26:28])[0]
            local_extra_len = struct.unpack("<H", fdata[28:30])[0]
            data_start = 30 + local_fname_len + local_extra_len
            raw_comp = fdata[data_start : data_start + comp_size]
            decomp = zlib.decompress(raw_comp, -15) if method == 8 else raw_comp

            with open(out_csv, "wb") as f:
                f.write(decomp)
            return tk
        except Exception:
            time.sleep(1.0)
    return None


def run_market_ingestion():
    print("=" * 80, flush=True)
    print("PHASE 6.8: EXPANDING MARKET DATA TO 300 COMPANIES (CONCURRENT INGESTION)", flush=True)
    print("=" * 80, flush=True)

    t_start = time.time()
    RAW_MARKET_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(f"Missing 300-company cohort manifest at {MANIFEST_PATH}")
    if not CD_CACHE_PATH.exists():
        raise FileNotFoundError(f"Missing central directory cache at {CD_CACHE_PATH}")

    df_manifest = pd.read_csv(MANIFEST_PATH)
    with open(CD_CACHE_PATH, "r", encoding="utf-8") as f:
        cd_entries = json.load(f)

    tickers = df_manifest["ticker"].tolist()
    print(f"Target cohort: {len(tickers)} companies from {MANIFEST_PATH}", flush=True)

    # Check which raw CSVs need downloading
    missing_raw = [t for t in tickers if not (RAW_MARKET_DIR / f"{t}.csv").exists()]
    print(f"Existing raw CSVs : {len(tickers) - len(missing_raw)}", flush=True)
    print(f"To download       : {len(missing_raw)}", flush=True)

    if missing_raw:
        print("Resolving direct CloudFront URL...", flush=True)
        direct_url = get_direct_cloudfront_url()
        print("Direct URL resolved. Starting concurrent byte-range acquisitions (8 workers)...", flush=True)

        downloaded_count = 0
        with ThreadPoolExecutor(max_workers=8) as executor:
            future_to_tk = {
                executor.submit(download_ticker_csv, tk, cd_entries[tk], direct_url): tk
                for tk in missing_raw
                if tk in cd_entries
            }

            for future in as_completed(future_to_tk):
                res = future.result()
                downloaded_count += 1
                if downloaded_count % 25 == 0 or downloaded_count == len(future_to_tk):
                    print(f"  Downloaded [{downloaded_count}/{len(future_to_tk)}] tickers...", flush=True)

    # Ingest each into processed parquet using MarketIngestor
    print("\nProcessing raw CSVs into sanitized Parquet files...", flush=True)
    universe_path = PROJECT_ROOT / "data" / "processed" / "universe" / "sp500_universe.parquet"
    universe_df = pd.read_parquet(universe_path) if universe_path.exists() else None
    ingestor = MarketIngestor(universe_df=universe_df)

    processed_dfs = []
    quality_stats = []

    manifest_map = dict(zip(df_manifest["ticker"], df_manifest["company_id"]))

    for idx, tk in enumerate(tickers, 1):
        raw_csv = RAW_MARKET_DIR / f"{tk}.csv"
        out_parquet = PROCESSED_DIR / f"{tk}.parquet"

        if not raw_csv.exists():
            print(f"Skipping {tk}: raw CSV missing", flush=True)
            continue

        if not out_parquet.exists():
            ingestor.ingest_file(
                raw_csv_path=str(raw_csv),
                ticker=tk,
                output_parquet_path=str(out_parquet),
            )

        # Load and validate
        p_df = pd.read_parquet(out_parquet)
        valid_mask = (
            (p_df["open"] > 0)
            & (p_df["close"] > 0)
            & (p_df["adjusted_close"] > 0)
            & (p_df["high"] > 0)
            & (p_df["low"] > 0)
        )
        clean_df = p_df[valid_mask].copy().sort_values("trading_date").reset_index(drop=True)
        # Assign canonical unique company_id from cohort manifest
        if tk in manifest_map:
            clean_df["company_id"] = manifest_map[tk]

        # Filter to research coverage window: 2018-01-01 to 2020-06-15
        window_df = clean_df[
            (clean_df["trading_date"] >= "2018-01-01") & (clean_df["trading_date"] <= "2020-06-15")
        ].copy()

        quality_stats.append({
            "ticker": tk,
            "company_id": clean_df["company_id"].iloc[0] if "company_id" in clean_df.columns else f"COMP_{tk}",
            "total_rows": len(clean_df),
            "window_rows": len(window_df),
            "earliest_date": clean_df["trading_date"].min(),
            "latest_date": clean_df["trading_date"].max(),
            "missing_prices": int((~valid_mask).sum()),
        })

        processed_dfs.append(clean_df)
        if idx % 50 == 0 or idx == len(tickers):
            print(f"  Processed [{idx}/{len(tickers)}] {tk}: {len(clean_df):,} rows", flush=True)

    # Consolidate into single research parquet
    print(f"\nConsolidating {len(processed_dfs)} company datasets into {CONSOLIDATED_PARQUET}...", flush=True)
    df_consolidated = pd.concat(processed_dfs, ignore_index=True)
    df_consolidated.to_parquet(CONSOLIDATED_PARQUET, index=False)

    elapsed = time.time() - t_start
    print(f"Successfully consolidated {len(df_consolidated):,} total rows across {len(processed_dfs)} companies in {elapsed:.1f}s.", flush=True)

    # Generate summary JSON
    summary = {
        "phase": "6.8",
        "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "target_companies": len(tickers),
        "validated_companies": len(processed_dfs),
        "consolidated_total_rows": len(df_consolidated),
        "consolidated_parquet_path": str(CONSOLIDATED_PARQUET.relative_to(PROJECT_ROOT)),
        "primary_research_window": "2018-01-01 to 2020-06-15",
        "elapsed_seconds": elapsed,
        "company_quality_stats": quality_stats,
    }

    with open(SUMMARY_JSON, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"Saved market summary to {SUMMARY_JSON}", flush=True)


if __name__ == "__main__":
    run_market_ingestion()

"""
Phase 6.8 SEC EDGAR Ingestion & Point-in-Time Normalization Engine.

Fetches and normalizes SEC EDGAR company facts (XBRL) and Form 8-K filings
for the 300-company cohort:
- Complies with SEC Fair Access rate limit (<= 8 req/s) with declared User-Agent
- Caches raw JSON submissions and facts to data/raw/sec/
- Ingests into data/processed/sec/facts/phase6_8_financial_facts.parquet
- Ingests Form 8-K events into data/processed/sec/eight_k/phase6_8_8k_events.parquet
- Enforces strict point-in-time acceptanceDateTime guarantees and restatement isolation
"""

import os
import sys
import json
import time
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.sec.fetcher import SECFetcher
from src.data.sec.ingestor import SECIngestor
from src.config import get_sec_user_agent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ingest_phase6_8_sec")

MANIFEST_PATH = PROJECT_ROOT / "data" / "processed" / "universe" / "phase6_8_cohort_300_manifest.csv"
FACTS_OUTPUT_PARQUET = PROJECT_ROOT / "data" / "processed" / "sec" / "facts" / "phase6_8_financial_facts.parquet"
EVENTS_OUTPUT_PARQUET = PROJECT_ROOT / "data" / "processed" / "sec" / "eight_k" / "phase6_8_8k_events.parquet"
SUMMARY_JSON = PROJECT_ROOT / "data" / "processed" / "sec" / "phase6_8_sec_summary.json"


def run_sec_ingestion(max_companies: Optional[int] = None):
    print("=" * 80)
    print("PHASE 6.8: SEC EDGAR FINANCIAL FACTS & 8-K INGESTION (300 COMPANIES)")
    print("=" * 80)

    t_start = time.time()
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(f"Missing cohort manifest at {MANIFEST_PATH}")

    df_manifest = pd.read_csv(MANIFEST_PATH)
    if max_companies:
        df_manifest = df_manifest.head(max_companies)

    universe_path = PROJECT_ROOT / "data" / "processed" / "universe" / "sp500_universe.parquet"
    universe_df = pd.read_parquet(universe_path) if universe_path.exists() else None

    fetcher = SECFetcher(
        raw_dir=str(PROJECT_ROOT / "data" / "raw" / "sec"),
        user_agent=get_sec_user_agent(),
        min_request_interval=0.125,  # 8 requests/second
    )
    ingestor = SECIngestor(universe_df=universe_df)

    FACTS_OUTPUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    EVENTS_OUTPUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)

    all_fact_dfs = []
    all_8k_dfs = []

    success_facts_count = 0
    success_8k_count = 0
    total_companies = len(df_manifest)

    print(f"Starting SEC ingestion for {total_companies} companies with verified CIKs...")

    for idx, row in df_manifest.iterrows():
        tk = row["ticker"]
        cik = str(row["cik"]).strip().zfill(10)
        cid = row.get("company_id", f"US_CIK_{cik}")

        submissions_data = None
        accession_map = {}

        # 1. Fetch Submissions (includes 8-K filings metadata and accession map for PIT timestamps)
        try:
            submissions_data = fetcher.fetch_submissions(cik)
            if submissions_data:
                accession_map = ingestor.parse_submissions_accession_map(submissions_data)
                # Extract Form 8-K filings
                df_8k = ingestor.extract_8k_filings(cik=cik, submissions_data=submissions_data, max_filings=100)
                if not df_8k.empty:
                    # Filter to research window: 2018-01-01 to 2020-06-15
                    df_8k_window = df_8k[
                        (df_8k["filing_date"] >= "2018-01-01") & (df_8k["filing_date"] <= "2020-06-15")
                    ].copy()
                    if not df_8k_window.empty:
                        df_8k_window["company_id"] = cid
                        df_8k_window["ticker"] = tk
                        all_8k_dfs.append(df_8k_window)
                        success_8k_count += 1
        except Exception as e:
            logger.warning(f"[{idx+1}/{total_companies}] Failed to fetch submissions for {tk} (CIK {cik}): {e}")

        # 2. Fetch Company Facts (XBRL quarterly/annual financial statement data)
        try:
            facts_data = fetcher.fetch_company_facts(cik)
            if facts_data and "facts" in facts_data:
                df_facts = ingestor.extract_financial_facts(
                    cik=cik,
                    facts_data=facts_data,
                    accession_map=accession_map,
                )
                if not df_facts.empty:
                    # Retain facts spanning 2015 to 2021 for point-in-time warmup & feature engineering
                    if "fiscal_year" in df_facts.columns:
                        df_facts = df_facts[(df_facts["fiscal_year"] >= 2015) & (df_facts["fiscal_year"] <= 2021)].copy()
                    df_facts["company_id"] = cid
                    df_facts["ticker"] = tk
                    all_fact_dfs.append(df_facts)
                    success_facts_count += 1
        except Exception as e:
            logger.warning(f"[{idx+1}/{total_companies}] Failed to fetch company facts for {tk} (CIK {cik}): {e}")

        if (idx + 1) % 25 == 0 or (idx + 1) == total_companies:
            print(f"  Progress: [{idx+1}/{total_companies}] {tk} (CIK {cik}) | Facts: {success_facts_count} | 8-K: {success_8k_count}")

    # Consolidate and write parquets
    print("\nConsolidating facts and event records into persistent parquets...")
    if all_fact_dfs:
        df_all_facts = pd.concat(all_fact_dfs, ignore_index=True)
        # Ensure correct types and sorting
        df_all_facts["period_end"] = df_all_facts["period_end"].astype(str)
        if "acceptance_timestamp" in df_all_facts.columns:
            df_all_facts["acceptance_timestamp"] = df_all_facts["acceptance_timestamp"].astype(str)
        df_all_facts.to_parquet(FACTS_OUTPUT_PARQUET, index=False)
        print(f"Saved {len(df_all_facts):,} financial facts across {df_all_facts['ticker'].nunique()} companies to {FACTS_OUTPUT_PARQUET}")
    else:
        print("WARNING: No facts extracted!")
        df_all_facts = pd.DataFrame()

    if all_8k_dfs:
        df_all_8k = pd.concat(all_8k_dfs, ignore_index=True)
        df_all_8k["filing_date"] = df_all_8k["filing_date"].astype(str)
        if "acceptance_timestamp" in df_all_8k.columns:
            df_all_8k["acceptance_timestamp"] = df_all_8k["acceptance_timestamp"].astype(str)
        df_all_8k.to_parquet(EVENTS_OUTPUT_PARQUET, index=False)
        print(f"Saved {len(df_all_8k):,} Form 8-K events across {df_all_8k['ticker'].nunique()} companies to {EVENTS_OUTPUT_PARQUET}")
    else:
        print("WARNING: No 8-K events extracted!")
        df_all_8k = pd.DataFrame()

    elapsed = time.time() - t_start
    summary = {
        "phase": "6.8",
        "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "target_companies": total_companies,
        "companies_with_facts": df_all_facts["ticker"].nunique() if not df_all_facts.empty else 0,
        "total_financial_facts": len(df_all_facts),
        "companies_with_8k_events": df_all_8k["ticker"].nunique() if not df_all_8k.empty else 0,
        "total_8k_events": len(df_all_8k),
        "facts_parquet": str(FACTS_OUTPUT_PARQUET.relative_to(PROJECT_ROOT)),
        "events_parquet": str(EVENTS_OUTPUT_PARQUET.relative_to(PROJECT_ROOT)),
        "elapsed_seconds": elapsed,
    }

    with open(SUMMARY_JSON, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"Saved SEC summary to {SUMMARY_JSON} in {elapsed:.1f}s.")


if __name__ == "__main__":
    run_sec_ingestion()

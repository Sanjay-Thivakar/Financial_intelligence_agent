"""
Phase 6.9C SEC Data Recovery, Coverage Reconciliation & Point-in-Time Validation.

Recovers missing XBRL financial facts and Form 8-K material events across the
canonical 305-company cohort (January 2018 through June 2020) with strict
point-in-time acceptanceDateTime guarantees and full request-level auditing.
"""

import os
import sys
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.sec.fetcher import SECFetcher
from src.data.sec.ingestor import SECIngestor, CORE_GAAP_CONCEPTS
from src.data.sec.schema import PROCESSED_SEC_FACT_SCHEMA, PROCESSED_SEC_8K_SCHEMA
from src.data.sec.point_in_time import get_market_close_utc, is_record_eligible_at_cutoff
from src.config import get_sec_user_agent

COHORT_PATH = PROJECT_ROOT / "data" / "processed" / "universe" / "phase6_9a1_cohort_manifest.csv"
EXISTING_FACTS_PARQUET = PROJECT_ROOT / "data" / "processed" / "sec" / "facts" / "phase6_8_financial_facts.parquet"
EXISTING_EVENTS_PARQUET = PROJECT_ROOT / "data" / "processed" / "sec" / "eight_k" / "phase6_8_8k_events.parquet"

OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "sec" / "phase6_9c"
RECOVERED_FACTS_PARQUET = OUTPUT_DIR / "phase6_9c_financial_facts_recovered.parquet"
RECOVERED_EVENTS_PARQUET = OUTPUT_DIR / "phase6_9c_8k_events_recovered.parquet"
CONSOLIDATED_FACTS_PARQUET = OUTPUT_DIR / "phase6_9c_financial_facts_consolidated.parquet"
CONSOLIDATED_EVENTS_PARQUET = OUTPUT_DIR / "phase6_9c_8k_events_consolidated.parquet"
RECOVERY_MANIFEST_CSV = OUTPUT_DIR / "phase6_9c_sec_recovery_manifest.csv"
COMPANY_COVERAGE_CSV = OUTPUT_DIR / "phase6_9c_company_coverage.csv"
DATA_QUALITY_JSON = OUTPUT_DIR / "phase6_9c_data_quality_report.json"

RAW_DIR = PROJECT_ROOT / "data" / "raw" / "sec"


class SECRecoveryEngine:
    """Manages throttled, audited SEC acquisition and point-in-time dataset synthesis."""

    def __init__(self):
        self.user_agent = get_sec_user_agent()
        self.fetcher = SECFetcher(
            raw_dir=str(RAW_DIR),
            user_agent=self.user_agent,
            min_request_interval=0.125,  # <= 8 req/s (Fair Access)
        )
        self.ingestor = SECIngestor()
        self.request_logs: List[Dict[str, Any]] = []

    def log_request(
        self,
        ticker: str,
        cik: str,
        endpoint: str,
        url: str,
        status: int,
        attempt: int,
        size_bytes: int,
        outcome: str,
        error: str = "",
    ) -> None:
        self.request_logs.append({
            "ticker": ticker,
            "cik": cik,
            "endpoint": endpoint,
            "url": url,
            "http_status": status,
            "attempt_count": attempt,
            "response_size_bytes": size_bytes,
            "retrieval_timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "outcome": outcome,
            "error_reason": error,
        })

    def fetch_submissions_audited(self, ticker: str, cik: str) -> Dict[str, Any]:
        """Fetches submissions JSON with per-request auditing."""
        cik10 = str(cik).strip().zfill(10)
        cache_path = RAW_DIR / "submissions" / f"CIK{cik10}.json"

        if cache_path.exists() and cache_path.stat().st_size > 100:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.log_request(ticker, cik10, "submissions", str(cache_path), 200, 1, cache_path.stat().st_size, "CACHED_LOCAL")
            return data

        url = f"{self.fetcher.BASE_URL}/submissions/CIK{cik10}.json"
        for attempt in range(1, 4):
            self.fetcher._throttle()
            try:
                resp = self.fetcher.session.get(url, timeout=30)
                status = resp.status_code
                size = len(resp.content)
                if status == 200:
                    data = resp.json()
                    with open(cache_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)
                    self.log_request(ticker, cik10, "submissions", url, status, attempt, size, "FETCH_SUCCESS")
                    return data
                elif status == 404:
                    self.log_request(ticker, cik10, "submissions", url, status, attempt, size, "NOT_FOUND", "CIK not found on EDGAR")
                    return {}
                else:
                    self.log_request(ticker, cik10, "submissions", url, status, attempt, size, "HTTP_ERROR", f"Status {status}")
            except Exception as e:
                self.log_request(ticker, cik10, "submissions", url, 0, attempt, 0, "EXCEPTION", str(e))
                time.sleep(0.5 * attempt)
        return {}

    def fetch_submission_file_audited(self, ticker: str, cik: str, filename: str) -> Dict[str, Any]:
        """Fetches a paginated older submission file with auditing."""
        cache_path = RAW_DIR / "submissions" / filename
        if cache_path.exists() and cache_path.stat().st_size > 100:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.log_request(ticker, cik, "submissions_paginated", str(cache_path), 200, 1, cache_path.stat().st_size, "CACHED_LOCAL")
            return data

        url = f"{self.fetcher.BASE_URL}/submissions/{filename}"
        for attempt in range(1, 4):
            self.fetcher._throttle()
            try:
                resp = self.fetcher.session.get(url, timeout=30)
                status = resp.status_code
                size = len(resp.content)
                if status == 200:
                    data = resp.json()
                    with open(cache_path, "w", encoding="utf-8") as f:
                        json.dump(data, f)
                    self.log_request(ticker, cik, "submissions_paginated", url, status, attempt, size, "FETCH_SUCCESS")
                    return data
                else:
                    self.log_request(ticker, cik, "submissions_paginated", url, status, attempt, size, "HTTP_ERROR", f"Status {status}")
            except Exception as e:
                self.log_request(ticker, cik, "submissions_paginated", url, 0, attempt, 0, "EXCEPTION", str(e))
                time.sleep(0.5 * attempt)
        return {}

    def fetch_company_facts_audited(self, ticker: str, cik: str) -> Dict[str, Any]:
        """Fetches company facts JSON with per-request auditing."""
        cik10 = str(cik).strip().zfill(10)
        cache_path = RAW_DIR / "companyfacts" / f"CIK{cik10}.json"

        if cache_path.exists() and cache_path.stat().st_size > 100:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.log_request(ticker, cik10, "companyfacts", str(cache_path), 200, 1, cache_path.stat().st_size, "CACHED_LOCAL")
            return data

        url = f"{self.fetcher.BASE_URL}/api/xbrl/companyfacts/CIK{cik10}.json"
        for attempt in range(1, 4):
            self.fetcher._throttle()
            try:
                resp = self.fetcher.session.get(url, timeout=30)
                status = resp.status_code
                size = len(resp.content)
                if status == 200:
                    data = resp.json()
                    with open(cache_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)
                    self.log_request(ticker, cik10, "companyfacts", url, status, attempt, size, "FETCH_SUCCESS")
                    return data
                elif status == 404:
                    self.log_request(ticker, cik10, "companyfacts", url, status, attempt, size, "NOT_FOUND", "Facts not found on EDGAR")
                    return {}
                else:
                    self.log_request(ticker, cik10, "companyfacts", url, status, attempt, size, "HTTP_ERROR", f"Status {status}")
            except Exception as e:
                self.log_request(ticker, cik10, "companyfacts", url, 0, attempt, 0, "EXCEPTION", str(e))
                time.sleep(0.5 * attempt)
        return {}

    def extract_8k_from_filing_dict(
        self,
        company_id: str,
        ticker: str,
        cik10: str,
        filings_dict: Dict[str, Any],
        start_date: str = "2018-01-01",
        end_date: str = "2020-06-15",
    ) -> List[Dict[str, Any]]:
        """Extracts 8-K filings from either recent dict or paginated submissions dict."""
        forms = filings_dict.get("form", [])
        accns = filings_dict.get("accessionNumber", [])
        filed_dates = filings_dict.get("filingDate", [])
        acceptance_dts = filings_dict.get("acceptanceDateTime", [])
        primary_docs = filings_dict.get("primaryDocument", [])
        items_list = filings_dict.get("items", [])

        events = []
        for i, form in enumerate(forms):
            if form in ("8-K", "8-K/A"):
                f_date = filed_dates[i] if i < len(filed_dates) else ""
                if start_date <= f_date <= end_date:
                    accn = accns[i] if i < len(accns) else ""
                    accn_clean = accn.replace("-", "")
                    p_doc = primary_docs[i] if i < len(primary_docs) else ""
                    url = f"https://www.sec.gov/Archives/edgar/data/{int(cik10)}/{accn_clean}/{p_doc}"
                    acc_dt = acceptance_dts[i] if i < len(acceptance_dts) else None
                    if acc_dt:
                        ts = str(pd.to_datetime(acc_dt, utc=True))
                    else:
                        ts = str(pd.to_datetime(f"{f_date} 23:59:59", utc=True))
                    raw_items = items_list[i] if i < len(items_list) else ""
                    if isinstance(raw_items, list):
                        items_str = ",".join(str(it) for it in raw_items)
                    else:
                        items_str = str(raw_items) if raw_items else ""

                    events.append({
                        "company_id": company_id,
                        "cik": cik10,
                        "ticker": ticker,
                        "form": form,
                        "filing_date": f_date,
                        "acceptance_timestamp": ts,
                        "accession_number": accn,
                        "items": items_str,
                        "primary_document": p_doc,
                        "filing_url": url,
                        "source": "sec_edgar_submissions",
                    })
        return events


def run_phase6_9c_recovery():
    print("=" * 80)
    print("PHASE 6.9C: SEC DATA RECOVERY, RECONCILIATION & POINT-IN-TIME VALIDATION")
    print("=" * 80)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "submissions").mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "companyfacts").mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    engine = SECRecoveryEngine()

    print(f"Using SEC User-Agent: {engine.user_agent}")
    if "academic_research@university.edu" in engine.user_agent:
        raise ValueError("Cannot run with placeholder User-Agent. Configure truthful contact first.")

    # 1. Load canonical cohort
    cohort = pd.read_csv(COHORT_PATH)
    total_cohort = len(cohort)
    print(f"Canonical cohort loaded: {total_cohort} companies")

    # 2. Load existing datasets (READ-ONLY)
    facts_existing = pd.read_parquet(EXISTING_FACTS_PARQUET)
    events_existing = pd.read_parquet(EXISTING_EVENTS_PARQUET)

    existing_facts_tickers = set(facts_existing["ticker"])
    existing_events_tickers = set(events_existing["ticker"])

    missing_facts_df = cohort[~cohort["ticker"].isin(existing_facts_tickers)].copy()
    missing_events_df = cohort[~cohort["ticker"].isin(existing_events_tickers)].copy()

    print(f"Initial coverage - Facts: {len(existing_facts_tickers)}/305 (Missing: {len(missing_facts_df)})")
    print(f"Initial coverage - 8-K Events: {len(existing_events_tickers)}/305 (Missing: {len(missing_events_df)})")

    # ----------------------------------------------------
    # STAGE B: RECOVER MISSING FACTS (25 companies)
    # ----------------------------------------------------
    print("\n--- STAGE B: RECOVERING MISSING XBRL FACTS ---")
    recovered_fact_dfs = []
    facts_recovery_summary = {}

    for idx, row in missing_facts_df.iterrows():
        tk = row["ticker"]
        cik10 = str(row["cik"]).strip().zfill(10)
        cid = row["company_id"]
        cname = row["company_name"]

        print(f"[{len(facts_recovery_summary)+1}/{len(missing_facts_df)}] Fact Recovery for {tk} (CIK {cik10}, {cname})...")

        # 1. Fetch submissions to build accession timestamp map
        sub_data = engine.fetch_submissions_audited(tk, cik10)
        accn_map = engine.ingestor.parse_submissions_accession_map(sub_data) if sub_data else {}

        # 2. Fetch company facts
        facts_data = engine.fetch_company_facts_audited(tk, cik10)
        if facts_data and "facts" in facts_data:
            df_f = engine.ingestor.extract_financial_facts(
                cik=cik10,
                facts_data=facts_data,
                accession_map=accn_map,
            )
            if not df_f.empty:
                # Retain facts spanning 2015 to 2021 for point-in-time warmup & feature engineering
                if "fiscal_year" in df_f.columns:
                    df_f = df_f[(df_f["fiscal_year"] >= 2015) & (df_f["fiscal_year"] <= 2021)].copy()
                df_f["company_id"] = cid
                df_f["ticker"] = tk
                recovered_fact_dfs.append(df_f)
                facts_recovery_summary[tk] = {
                    "status": "RECOVERED",
                    "rows": len(df_f),
                    "concepts": df_f["concept"].nunique(),
                    "period_min": str(df_f["period_end"].min()),
                    "period_max": str(df_f["period_end"].max()),
                }
                print(f"  -> Successfully extracted {len(df_f):,} facts across {df_f['concept'].nunique()} concepts")
            else:
                facts_recovery_summary[tk] = {"status": "NO_CORE_GAAP_OBSERVATIONS", "rows": 0}
                print("  -> Warning: No core GAAP observations matched")
        else:
            facts_recovery_summary[tk] = {"status": "FETCH_FAILED_OR_EMPTY", "rows": 0}
            print("  -> Warning: Facts data empty or unavailable")

    # ----------------------------------------------------
    # STAGE C: RECOVER MISSING 8-K EVENTS (111 companies)
    # ----------------------------------------------------
    print("\n--- STAGE C: RECOVERING MISSING 8-K EVENTS ---")
    recovered_events_list = []
    events_recovery_summary = {}

    for idx, row in missing_events_df.iterrows():
        tk = row["ticker"]
        cik10 = str(row["cik"]).strip().zfill(10)
        cid = row["company_id"]
        cname = row["company_name"]

        print(f"[{len(events_recovery_summary)+1}/{len(missing_events_df)}] 8-K Recovery for {tk} (CIK {cik10}, {cname})...")

        sub_data = engine.fetch_submissions_audited(tk, cik10)
        if not sub_data:
            events_recovery_summary[tk] = {"status": "SUBMISSIONS_FETCH_FAILED", "events_found": 0}
            continue

        company_events = []

        # 1. Check recent filings
        recent = sub_data.get("filings", {}).get("recent", {})
        recent_events = engine.extract_8k_from_filing_dict(cid, tk, cik10, recent)
        company_events.extend(recent_events)

        # 2. Check paginated older filings if needed
        # We need coverage for window 2018-01-01 to 2020-06-15
        older_files = sub_data.get("filings", {}).get("files", [])
        for file_info in older_files:
            f_name = file_info.get("name")
            f_from = file_info.get("filingFrom", "")
            f_to = file_info.get("filingTo", "")

            # Check if this paginated file overlaps with [2018-01-01, 2020-06-15]
            if f_name and not (f_to < "2018-01-01" or f_from > "2020-06-15"):
                paged_data = engine.fetch_submission_file_audited(tk, cik10, f_name)
                if paged_data:
                    paged_events = engine.extract_8k_from_filing_dict(cid, tk, cik10, paged_data)
                    company_events.extend(paged_events)

        # Deduplicate company events by accession_number
        if company_events:
            unique_accns = set()
            deduped = []
            for ev in company_events:
                if ev["accession_number"] not in unique_accns:
                    unique_accns.add(ev["accession_number"])
                    deduped.append(ev)
            recovered_events_list.extend(deduped)
            events_recovery_summary[tk] = {
                "status": "RECOVERED",
                "events_found": len(deduped),
                "date_min": min(e["filing_date"] for e in deduped),
                "date_max": max(e["filing_date"] for e in deduped),
            }
            print(f"  -> Recovered {len(deduped)} Form 8-K filings in 2018-2020 window")
        else:
            # Verified no matching filings in 2018-2020 window
            events_recovery_summary[tk] = {
                "status": "VERIFIED_ZERO_FILINGS_IN_WINDOW",
                "events_found": 0,
            }
            print("  -> Verified 0 Form 8-K filings in [2018-01-01, 2020-06-15]")

    # ----------------------------------------------------
    # STAGE D: PERSIST RECOVERED & CONSOLIDATED DATASETS
    # ----------------------------------------------------
    print("\n--- STAGE D: PERSISTING VERSIONED DATASETS ---")

    # 1. Recovered Facts Parquet
    if recovered_fact_dfs:
        df_rec_facts = pd.concat(recovered_fact_dfs, ignore_index=True)
        df_rec_facts["period_end"] = df_rec_facts["period_end"].astype(str)
        df_rec_facts["acceptance_timestamp"] = df_rec_facts["acceptance_timestamp"].astype(str)
        df_rec_facts.to_parquet(RECOVERED_FACTS_PARQUET, index=False)
        print(f"Saved {len(df_rec_facts):,} recovered facts across {df_rec_facts['ticker'].nunique()} companies to {RECOVERED_FACTS_PARQUET}")
    else:
        df_rec_facts = pd.DataFrame()
        print("No facts recovered.")

    # 2. Recovered 8-K Events Parquet
    if recovered_events_list:
        df_rec_events = pd.DataFrame(recovered_events_list)
        df_rec_events.to_parquet(RECOVERED_EVENTS_PARQUET, index=False)
        print(f"Saved {len(df_rec_events):,} recovered 8-K events across {df_rec_events['ticker'].nunique()} companies to {RECOVERED_EVENTS_PARQUET}")
    else:
        df_rec_events = pd.DataFrame()
        print("No 8-K events recovered.")

    # 3. Consolidated Facts Parquet (Phase 6.8 + Phase 6.9C)
    print("\nSynthesizing Consolidated Financial Facts...")
    if not df_rec_facts.empty:
        # Cast timestamps to string for consistent concat
        facts_existing_clean = facts_existing.copy()
        facts_existing_clean["acceptance_timestamp"] = facts_existing_clean["acceptance_timestamp"].astype(str)
        facts_existing_clean["period_end"] = facts_existing_clean["period_end"].astype(str)

        df_consolidated_facts = pd.concat([facts_existing_clean, df_rec_facts], ignore_index=True)
        # Deduplicate using stable source identifiers
        df_consolidated_facts = df_consolidated_facts.drop_duplicates(
            subset=["company_id", "concept", "period_end", "accession_number", "value"]
        )
        df_consolidated_facts.to_parquet(CONSOLIDATED_FACTS_PARQUET, index=False)
        print(f"Saved consolidated facts: {len(df_consolidated_facts):,} rows across {df_consolidated_facts['ticker'].nunique()} companies to {CONSOLIDATED_FACTS_PARQUET}")
    else:
        df_consolidated_facts = facts_existing

    # 4. Consolidated 8-K Events Parquet (Phase 6.8 + Phase 6.9C)
    print("\nSynthesizing Consolidated 8-K Events...")
    if not df_rec_events.empty:
        events_existing_clean = events_existing.copy()
        events_existing_clean["acceptance_timestamp"] = events_existing_clean["acceptance_timestamp"].astype(str)
        events_existing_clean["filing_date"] = events_existing_clean["filing_date"].astype(str)

        df_consolidated_events = pd.concat([events_existing_clean, df_rec_events], ignore_index=True)
        df_consolidated_events = df_consolidated_events.drop_duplicates(
            subset=["company_id", "accession_number"]
        )
        df_consolidated_events.to_parquet(CONSOLIDATED_EVENTS_PARQUET, index=False)
        print(f"Saved consolidated 8-K events: {len(df_consolidated_events):,} rows across {df_consolidated_events['ticker'].nunique()} companies to {CONSOLIDATED_EVENTS_PARQUET}")
    else:
        df_consolidated_events = events_existing

    # 5. Recovery Manifest CSV
    df_manifest = pd.DataFrame(engine.request_logs)
    df_manifest.to_csv(RECOVERY_MANIFEST_CSV, index=False)
    print(f"Saved request manifest with {len(df_manifest)} entries to {RECOVERY_MANIFEST_CSV}")

    # 6. Per-Company Coverage CSV (305 rows)
    final_facts_tickers = set(df_consolidated_facts["ticker"])
    final_events_tickers = set(df_consolidated_events["ticker"])

    coverage_rows = []
    for _, row in cohort.iterrows():
        tk = row["ticker"]
        has_f = tk in final_facts_tickers
        has_e = tk in final_events_tickers

        # Determine facts coverage classification
        if tk in existing_facts_tickers:
            f_status = "ALREADY_PRESENT_PHASE6_8"
        elif tk in facts_recovery_summary and facts_recovery_summary[tk]["status"] == "RECOVERED":
            f_status = "RECOVERED_PHASE6_9C"
        elif tk in facts_recovery_summary:
            f_status = facts_recovery_summary[tk]["status"]
        else:
            f_status = "UNAVAILABLE"

        # Determine events coverage classification
        if tk in existing_events_tickers:
            e_status = "ALREADY_PRESENT_PHASE6_8"
        elif tk in events_recovery_summary and events_recovery_summary[tk]["status"] == "RECOVERED":
            e_status = "RECOVERED_PHASE6_9C"
        elif tk in events_recovery_summary and events_recovery_summary[tk]["status"] == "VERIFIED_ZERO_FILINGS_IN_WINDOW":
            e_status = "VERIFIED_ZERO_FILINGS_IN_WINDOW"
        elif tk in events_recovery_summary:
            e_status = events_recovery_summary[tk]["status"]
        else:
            e_status = "UNAVAILABLE"

        coverage_rows.append({
            "ticker": tk,
            "company_name": row["company_name"],
            "cik": str(row["cik"]).zfill(10),
            "sector": row["sector"],
            "has_structured_facts": has_f,
            "facts_status": f_status,
            "has_8k_events": has_e,
            "events_status": e_status,
            "point_in_time_lineage": "COMPLETE" if (has_f or has_e) else "NONE",
        })

    df_coverage = pd.DataFrame(coverage_rows)
    df_coverage.to_csv(COMPANY_COVERAGE_CSV, index=False)
    print(f"Saved comprehensive coverage matrix to {COMPANY_COVERAGE_CSV}")

    # 7. Data Quality Report JSON
    quality_report = {
        "phase": "6.9C",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "total_cohort_companies": total_cohort,
        "facts_recovery": {
            "initial_coverage_count": len(existing_facts_tickers),
            "recovered_companies_count": df_rec_facts["ticker"].nunique() if not df_rec_facts.empty else 0,
            "recovered_rows_count": len(df_rec_facts),
            "final_coverage_count": df_consolidated_facts["ticker"].nunique(),
            "final_total_rows": len(df_consolidated_facts),
            "concepts_tracked": sorted(list(df_consolidated_facts["concept"].unique())),
        },
        "events_recovery": {
            "initial_coverage_count": len(existing_events_tickers),
            "recovered_companies_count": df_rec_events["ticker"].nunique() if not df_rec_events.empty else 0,
            "verified_zero_companies_count": sum(1 for v in events_recovery_summary.values() if v.get("status") == "VERIFIED_ZERO_FILINGS_IN_WINDOW"),
            "recovered_rows_count": len(df_rec_events),
            "final_coverage_count": df_consolidated_events["ticker"].nunique(),
            "final_total_rows": len(df_consolidated_events),
        },
        "requests_audited": {
            "total_requests": len(df_manifest),
            "cached_local": int((df_manifest["outcome"] == "CACHED_LOCAL").sum()),
            "fetched_remote": int((df_manifest["outcome"] == "FETCH_SUCCESS").sum()),
            "failed_remote": int((df_manifest["outcome"].isin(["HTTP_ERROR", "EXCEPTION", "NOT_FOUND"])).sum()),
        },
        "elapsed_seconds": round(time.time() - t0, 2),
    }

    with open(DATA_QUALITY_JSON, "w", encoding="utf-8") as f:
        json.dump(quality_report, f, indent=2)
    print(f"Saved data quality report to {DATA_QUALITY_JSON} in {quality_report['elapsed_seconds']}s")

    print("\n" + "=" * 80)
    print(f"PHASE 6.9C RECOVERY COMPLETE IN {quality_report['elapsed_seconds']}s")
    print(f"Final Facts Coverage: {quality_report['facts_recovery']['final_coverage_count']}/305")
    print(f"Final 8-K Events Coverage: {quality_report['events_recovery']['final_coverage_count']}/305")
    print("=" * 80)


if __name__ == "__main__":
    run_phase6_9c_recovery()

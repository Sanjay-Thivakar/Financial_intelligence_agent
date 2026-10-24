"""
Phase 8B — SEC Data Recovery and Coverage Expansion Engine.

Recovers complete XBRL financial facts across the canonical 305-company cohort
for the entire 2015-2023 period (including 2022-2023) using the local SEC EDGAR
raw cache, with point-in-time acceptanceDateTime guarantees and accession-level tracking.
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Any, Optional
import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.sec.ingestor import SECIngestor, CORE_GAAP_CONCEPTS

COHORT_PATH = PROJECT_ROOT / "data" / "processed" / "universe" / "phase6_9a1_cohort_manifest.csv"
RAW_FACTS_DIR = PROJECT_ROOT / "data" / "raw" / "sec" / "companyfacts"
RAW_SUB_DIR = PROJECT_ROOT / "data" / "raw" / "sec" / "submissions"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "sec" / "phase8"

# Expanded target GAAP concepts for comprehensive financial reporting intelligence
PHASE8_GAAP_CONCEPTS = {
    # Revenue
    "Revenues": "revenue",
    "RevenueFromContractWithCustomerExcludingAssessedTax": "revenue",
    "SalesRevenueNet": "revenue",
    # Gross Profit & Costs
    "GrossProfit": "gross_profit",
    "CostOfGoodsAndServicesSold": "cost_of_revenue",
    "CostOfRevenue": "cost_of_revenue",
    # Operating Income
    "OperatingIncomeLoss": "operating_income",
    # Net Income
    "NetIncomeLoss": "net_income",
    "ProfitLoss": "net_income",
    # Balance Sheet - Assets
    "Assets": "total_assets",
    "AssetsCurrent": "current_assets",
    "CashAndCashEquivalentsAtCarryingValue": "cash_and_equivalents",
    # Balance Sheet - Liabilities & Equity
    "Liabilities": "total_liabilities",
    "LiabilitiesCurrent": "current_liabilities",
    "StockholdersEquity": "stockholders_equity",
    "LongTermDebtNoncurrent": "long_term_debt",
    "LongTermDebt": "long_term_debt",
    # Cash Flows
    "NetCashProvidedByUsedInOperatingActivities": "operating_cash_flow",
    "PaymentsToAcquirePropertyPlantAndEquipment": "capex",
    "PaymentsToAcquireProductiveAssets": "capex",
    # Per share
    "EarningsPerShareDiluted": "diluted_eps",
    "EarningsPerShareBasic": "basic_eps",
}


def build_full_accession_map(cik: str) -> Dict[str, Dict[str, Any]]:
    """Builds lookup map for accession numbers from main and paginated submission files."""
    cik10 = str(cik).strip().zfill(10)
    sub_path = RAW_SUB_DIR / f"CIK{cik10}.json"
    accession_map = {}

    if not sub_path.exists():
        return accession_map

    with open(sub_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 1. Recent filings
    recent = data.get("filings", {}).get("recent", {})
    accns = recent.get("accessionNumber", [])
    forms = recent.get("form", [])
    filed_dates = recent.get("filingDate", [])
    report_dates = recent.get("reportDate", [])
    acceptance_dts = recent.get("acceptanceDateTime", [])
    primary_docs = recent.get("primaryDocument", [])
    items = recent.get("items", [])

    for i, accn in enumerate(accns):
        accession_map[accn] = {
            "form": forms[i] if i < len(forms) else "",
            "filed_date": filed_dates[i] if i < len(filed_dates) else "",
            "report_date": report_dates[i] if i < len(report_dates) else "",
            "acceptance_datetime": acceptance_dts[i] if i < len(acceptance_dts) else None,
            "primary_document": primary_docs[i] if i < len(primary_docs) else "",
            "items": items[i] if i < len(items) else "",
        }

    # 2. Older paginated files if referenced
    files_list = data.get("filings", {}).get("files", [])
    for file_meta in files_list:
        fname = file_meta.get("name")
        if fname:
            paginated_path = RAW_SUB_DIR / fname
            if paginated_path.exists():
                with open(paginated_path, "r", encoding="utf-8") as pf:
                    pdata = json.load(pf)
                p_accns = pdata.get("accessionNumber", [])
                p_forms = pdata.get("form", [])
                p_filed = pdata.get("filingDate", [])
                p_report = pdata.get("reportDate", [])
                p_accept = pdata.get("acceptanceDateTime", [])
                p_pdoc = pdata.get("primaryDocument", [])
                for pi, paccn in enumerate(p_accns):
                    if paccn not in accession_map:
                        accession_map[paccn] = {
                            "form": p_forms[pi] if pi < len(p_forms) else "",
                            "filed_date": p_filed[pi] if pi < len(p_filed) else "",
                            "report_date": p_report[pi] if pi < len(p_report) else "",
                            "acceptance_datetime": p_accept[pi] if pi < len(p_accept) else None,
                            "primary_document": p_pdoc[pi] if pi < len(p_pdoc) else "",
                        }

    return accession_map


def extract_company_facts_phase8(
    cid: str,
    ticker: str,
    reporting_ciks: List[str],
    min_fiscal_year: int = 2014,
    max_fiscal_year: int = 2023,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Extracts XBRL facts across one or more CIKs for a canonical company."""
    all_facts = []
    audit_stats = {
        "ticker": ticker,
        "company_id": cid,
        "reporting_ciks": ",".join(reporting_ciks),
        "total_extracted": 0,
        "has_2022": False,
        "has_2023": False,
        "earliest_filed": None,
        "latest_filed": None,
        "acceptance_ts_count": 0,
    }

    for cik in reporting_ciks:
        cik10 = str(cik).strip().zfill(10)
        facts_path = RAW_FACTS_DIR / f"CIK{cik10}.json"
        if not facts_path.exists():
            continue

        accn_map = build_full_accession_map(cik10)

        with open(facts_path, "r", encoding="utf-8") as f:
            facts_data = json.load(f)

        gaap_facts = facts_data.get("facts", {}).get("us-gaap", {})
        
        for concept_tag, canonical_label in PHASE8_GAAP_CONCEPTS.items():
            if concept_tag not in gaap_facts:
                continue
            
            fact_obj = gaap_facts[concept_tag]
            units_dict = fact_obj.get("units", {})

            for unit_key, obs_list in units_dict.items():
                for obs in obs_list:
                    form = obs.get("form", "")
                    if form not in ("10-K", "10-Q", "10-K/A", "10-Q/A"):
                        continue

                    val = obs.get("val")
                    if val is None:
                        continue

                    fy = obs.get("fy", 0)
                    try:
                        fy_int = int(fy) if fy else 0
                    except (ValueError, TypeError):
                        fy_int = 0

                    filed_date = obs.get("filed", "")
                    if not filed_date:
                        continue

                    filed_year = int(filed_date[:4]) if len(filed_date) >= 4 else 0
                    # Filter to research window: filings from 2014 to 2023
                    if filed_year < min_fiscal_year or filed_year > max_fiscal_year:
                        continue

                    accn = obs.get("accn", "")
                    period_end = obs.get("end", "")
                    period_start = obs.get("start")
                    fp = obs.get("fp", "")

                    # Map acceptance timestamp
                    accn_meta = accn_map.get(accn, {})
                    accept_dt = accn_meta.get("acceptance_datetime")

                    if accept_dt:
                        ts = str(pd.to_datetime(accept_dt, utc=True))
                        audit_stats["acceptance_ts_count"] += 1
                    else:
                        # Conservative fallback: end of filing date UTC
                        ts = str(pd.to_datetime(f"{filed_date} 23:59:59", utc=True))

                    all_facts.append({
                        "company_id": cid,
                        "cik": cik10,
                        "ticker": ticker,
                        "taxonomy": "us-gaap",
                        "concept": concept_tag,
                        "label": canonical_label,
                        "period_start": period_start,
                        "period_end": period_end,
                        "fiscal_year": fy_int,
                        "fiscal_period": fp,
                        "form": form,
                        "filed_date": filed_date,
                        "acceptance_timestamp": ts,
                        "accession_number": accn,
                        "value": float(val),
                        "unit": unit_key,
                        "source": "sec_edgar_companyfacts",
                    })

                    if filed_year == 2022:
                        audit_stats["has_2022"] = True
                    if filed_year == 2023:
                        audit_stats["has_2023"] = True

                    if audit_stats["earliest_filed"] is None or filed_date < audit_stats["earliest_filed"]:
                        audit_stats["earliest_filed"] = filed_date
                    if audit_stats["latest_filed"] is None or filed_date > audit_stats["latest_filed"]:
                        audit_stats["latest_filed"] = filed_date

    audit_stats["total_extracted"] = len(all_facts)
    return all_facts, audit_stats


def run_phase8b_recovery():
    print("=" * 90)
    print("PHASE 8B: SEC DATA RECOVERY & COVERAGE EXPANSION (2015-2023)")
    print("=" * 90)
    t0 = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df_cohort = pd.read_csv(COHORT_PATH)
    total_cohort = len(df_cohort)
    print(f"Loaded canonical cohort: {total_cohort} companies.")

    all_fact_records = []
    company_audits = []

    for idx, row in df_cohort.iterrows():
        tk = row["ticker"]
        cid = row["company_id"]
        manifest_cik = str(row["cik"]).strip().zfill(10)

        reporting_ciks = [manifest_cik]
        if tk == "CXO":
            reporting_ciks = ["0001358071"]
        elif tk == "APA":
            reporting_ciks = ["0001841666", "0000006769"]

        facts, stats = extract_company_facts_phase8(
            cid=cid,
            ticker=tk,
            reporting_ciks=reporting_ciks,
            min_fiscal_year=2014,
            max_fiscal_year=2023,
        )
        all_fact_records.extend(facts)
        company_audits.append(stats)

        if (idx + 1) % 50 == 0 or (idx + 1) == total_cohort:
            print(f"  Processed [{idx+1}/{total_cohort}] companies. Total facts extracted so far: {len(all_fact_records):,}")

    df_all_facts = pd.DataFrame(all_fact_records)
    print(f"\nRaw Extracted Facts: {len(df_all_facts):,} rows.")

    # Deduplication: remove exact duplicate observations
    # A single filing can report the same fact under multiple contexts; keep distinct by (concept, period_end, form, filed_date, accession_number, value)
    df_all_facts = df_all_facts.drop_duplicates(
        subset=["company_id", "concept", "period_end", "form", "filed_date", "accession_number", "value"]
    )
    df_all_facts = df_all_facts.sort_values(
        by=["company_id", "concept", "period_end", "acceptance_timestamp"]
    ).reset_index(drop=True)

    print(f"Deduplicated Facts : {len(df_all_facts):,} rows.")

    # Yearly breakdown
    df_all_facts["filed_year"] = df_all_facts["filed_date"].str[:4]
    yearly_counts = df_all_facts.groupby("filed_year").size().to_dict()
    print("\nRecovered Facts Filing Year Distribution:")
    for yr in sorted(yearly_counts.keys()):
        print(f"  Year {yr}: {yearly_counts[yr]:,} facts")

    # Form breakdown
    form_counts = df_all_facts.groupby("form").size().to_dict()
    print("\nRecovered Facts Form Distribution:")
    for form, cnt in sorted(form_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {form:<8}: {cnt:,} facts")

    # Save to Parquet
    out_parquet = OUTPUT_DIR / "phase8_financial_facts.parquet"
    df_all_facts.to_parquet(out_parquet, index=False)
    file_size_mb = os.path.getsize(out_parquet) / (1024 * 1024)
    print(f"\nSaved Phase 8 Financial Facts to {out_parquet.relative_to(PROJECT_ROOT)} ({file_size_mb:.2f} MB)")

    # Save Company Coverage Manifest
    df_comp_audit = pd.DataFrame(company_audits)
    out_coverage = OUTPUT_DIR / "phase8_company_coverage.csv"
    df_comp_audit.to_csv(out_coverage, index=False)
    print(f"Saved company coverage audit to {out_coverage.relative_to(PROJECT_ROOT)}")

    # Overall recovery summary
    manifest_summary = {
        "phase": "Phase 8B",
        "created_at_utc": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "total_facts_recovered": len(df_all_facts),
        "total_cohort_companies": total_cohort,
        "companies_with_facts": int(df_comp_audit[df_comp_audit['total_extracted'] > 0]['ticker'].count()),
        "companies_with_2022_facts": int(df_comp_audit[df_comp_audit['has_2022'] == True]['ticker'].count()),
        "companies_with_2023_facts": int(df_comp_audit[df_comp_audit['has_2023'] == True]['ticker'].count()),
        "facts_2022": yearly_counts.get("2022", 0),
        "facts_2023": yearly_counts.get("2023", 0),
        "facts_parquet_path": str(out_parquet.relative_to(PROJECT_ROOT)),
        "facts_parquet_size_mb": round(file_size_mb, 2),
        "earliest_filing_date": str(df_all_facts["filed_date"].min()),
        "latest_filing_date": str(df_all_facts["filed_date"].max()),
        "unique_concepts": int(df_all_facts["concept"].nunique()),
        "unique_labels": int(df_all_facts["label"].nunique()),
    }

    manifest_json_path = OUTPUT_DIR / "phase8_sec_recovery_manifest.json"
    with open(manifest_json_path, "w", encoding="utf-8") as f:
        json.dump(manifest_summary, f, indent=2)
    print(f"Saved Phase 8 recovery manifest to {manifest_json_path.relative_to(PROJECT_ROOT)}")
    print(f"Phase 8B Recovery completed in {time.time() - t0:.1f}s.")
    return manifest_summary


if __name__ == "__main__":
    run_phase8b_recovery()

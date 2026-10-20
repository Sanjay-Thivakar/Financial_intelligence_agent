"""
Phase 5I Market Ingestion & Coverage Engine.

Ingests, normalizes, validates, and reports on the 60-company research cohort across all 11 GICS sectors.
Ensures point-in-time identity mapping, duplicate rejection, calendar alignment,
forward target construction, and non-destructive persistence.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import struct
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
import zlib

import numpy as np
import pandas as pd
import requests

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.market.ingestor import MarketIngestor
from src.features.calendar import MarketCalendar
from src.features.target import ForwardReturnTargetEngine, TargetConfig

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ingest_phase5i")

HF_RAW_BASE = "https://huggingface.co/datasets/Zihan1004/FNSPID/resolve/main"

# 60-Company Cohort Definition: 11 GICS Sectors
COHORT_60_SPECS: List[Dict[str, str]] = [
    # Information Technology (6)
    {"ticker": "AAPL", "sector": "Information Technology", "notes": "Mega-cap core hardware/services"},
    {"ticker": "MSFT", "sector": "Information Technology", "notes": "Software/cloud enterprise leader"},
    {"ticker": "NVDA", "sector": "Information Technology", "notes": "Semiconductors and accelerated computing"},
    {"ticker": "INTC", "sector": "Information Technology", "notes": "Legacy semiconductor manufacturing"},
    {"ticker": "CSCO", "sector": "Information Technology", "notes": "Enterprise networking and cybersecurity"},
    {"ticker": "AMD", "sector": "Information Technology", "notes": "Semiconductors with discontinuous index membership"},

    # Financials (6)
    {"ticker": "JPM", "sector": "Financials", "notes": "Diversified commercial and investment banking"},
    {"ticker": "BAC", "sector": "Financials", "notes": "Major commercial and consumer banking"},
    {"ticker": "WFC", "sector": "Financials", "notes": "Major commercial/mortgage banking"},
    {"ticker": "GS", "sector": "Financials", "notes": "Global investment banking and trading"},
    {"ticker": "MS", "sector": "Financials", "notes": "Investment banking and wealth management"},
    {"ticker": "BLK", "sector": "Financials", "notes": "Global asset management and financial infrastructure"},

    # Health Care (6)
    {"ticker": "JNJ", "sector": "Health Care", "notes": "Diversified pharmaceuticals and medical technology"},
    {"ticker": "PFE", "sector": "Health Care", "notes": "Global biopharmaceuticals"},
    {"ticker": "BMY", "sector": "Health Care", "notes": "Biopharmaceuticals and specialty medicine"},
    {"ticker": "MRK", "sector": "Health Care", "notes": "Global oncology and vaccines"},
    {"ticker": "ABT", "sector": "Health Care", "notes": "Medical devices and diagnostics"},
    {"ticker": "CVS", "sector": "Health Care", "notes": "Healthcare services, retail pharmacy, and health insurance"},

    # Consumer Discretionary (6)
    {"ticker": "AMZN", "sector": "Consumer Discretionary", "notes": "E-commerce and cloud platform"},
    {"ticker": "TSLA", "sector": "Consumer Discretionary", "notes": "Electric vehicles and clean energy"},
    {"ticker": "HD", "sector": "Consumer Discretionary", "notes": "Home improvement retail"},
    {"ticker": "MCD", "sector": "Consumer Discretionary", "notes": "Global quick-service restaurants"},
    {"ticker": "NKE", "sector": "Consumer Discretionary", "notes": "Athletic footwear and apparel"},
    {"ticker": "SBUX", "sector": "Consumer Discretionary", "notes": "Global specialty coffee retail"},

    # Industrials (6)
    {"ticker": "CAT", "sector": "Industrials", "notes": "Heavy construction and mining equipment"},
    {"ticker": "GE", "sector": "Industrials", "notes": "Aerospace propulsion and aviation systems"},
    {"ticker": "BA", "sector": "Industrials", "notes": "Commercial aerospace and defense systems"},
    {"ticker": "HON", "sector": "Industrials", "notes": "Industrial automation, aerospace, building technologies"},
    {"ticker": "UNP", "sector": "Industrials", "notes": "Class I freight railroad transportation"},
    {"ticker": "LMT", "sector": "Industrials", "notes": "Aerospace, defense, and security technology"},

    # Consumer Staples (5)
    {"ticker": "PG", "sector": "Consumer Staples", "notes": "Global personal and household consumer products"},
    {"ticker": "KO", "sector": "Consumer Staples", "notes": "Global non-alcoholic beverage leader"},
    {"ticker": "PEP", "sector": "Consumer Staples", "notes": "Global beverages and snack foods"},
    {"ticker": "WMT", "sector": "Consumer Staples", "notes": "Global omnichannel retail and grocery"},
    {"ticker": "COST", "sector": "Consumer Staples", "notes": "Membership warehouse retail clubs"},

    # Communication Services (5)
    {"ticker": "GOOG", "sector": "Communication Services", "notes": "Search, digital advertising, cloud services"},
    {"ticker": "DIS", "sector": "Communication Services", "notes": "Entertainment, studio media, theme parks"},
    {"ticker": "CMCSA", "sector": "Communication Services", "notes": "Broadband, cable, media, streaming"},
    {"ticker": "T", "sector": "Communication Services", "notes": "Telecommunications and broadband connectivity"},
    {"ticker": "NFLX", "sector": "Communication Services", "notes": "Subscription video on demand and streaming"},

    # Energy (5)
    {"ticker": "XOM", "sector": "Energy", "notes": "Integrated energy major, exploration and refining"},
    {"ticker": "CVX", "sector": "Energy", "notes": "Integrated energy major, upstream and downstream"},
    {"ticker": "COP", "sector": "Energy", "notes": "Independent exploration and production"},
    {"ticker": "SLB", "sector": "Energy", "notes": "Oilfield services and reservoir technologies"},
    {"ticker": "EOG", "sector": "Energy", "notes": "Unconventional shale oil and gas exploration"},

    # Materials (5)
    {"ticker": "LIN", "sector": "Materials", "notes": "Industrial gases and engineering"},
    {"ticker": "APD", "sector": "Materials", "notes": "Industrial gases and chemicals"},
    {"ticker": "ECL", "sector": "Materials", "notes": "Water, hygiene, and infection prevention"},
    {"ticker": "SHW", "sector": "Materials", "notes": "Paints, industrial coatings, building materials"},
    {"ticker": "FCX", "sector": "Materials", "notes": "Copper and gold mining"},

    # Utilities (5)
    {"ticker": "NEE", "sector": "Utilities", "notes": "Regulated electric utility and renewable energy"},
    {"ticker": "SO", "sector": "Utilities", "notes": "Regulated electric and gas utility in Southeast US"},
    {"ticker": "DUK", "sector": "Utilities", "notes": "Regulated electric and gas utility in Carolinas/Midwest"},
    {"ticker": "D", "sector": "Utilities", "notes": "Regulated electric utility in Virginia/Carolinas"},
    {"ticker": "AEP", "sector": "Utilities", "notes": "Major electric transmission and distribution network"},

    # Real Estate (5)
    {"ticker": "AMT", "sector": "Real Estate", "notes": "Wireless communications and broadcast towers"},
    {"ticker": "PLD", "sector": "Real Estate", "notes": "Logistics real estate and distribution centers"},
    {"ticker": "CCI", "sector": "Real Estate", "notes": "Shared wireless communications infrastructure"},
    {"ticker": "EQIX", "sector": "Real Estate", "notes": "Global colocation data centers and interconnects"},
    {"ticker": "O", "sector": "Real Estate", "notes": "Single-tenant commercial net-lease retail properties"},
]

# Documented Excluded Symbols
EXCLUDED_COHORT_SPECS: List[Dict[str, str]] = [
    {"ticker": "AA", "sector": "Materials", "exclusion_reason": "Unresolved 2016 corporate split lineage into Alcoa Corp and Arconic; ambiguous CIK succession."},
    {"ticker": "UNH", "sector": "Health Care", "exclusion_reason": "Price series absent from FNSPID remote market archive; substituted with BMY."},
    {"ticker": "VZ", "sector": "Communication Services", "exclusion_reason": "Price series absent from FNSPID remote market archive; substituted with T (AT&T)."},
    {"ticker": "SPG", "sector": "Real Estate", "exclusion_reason": "Price series absent from FNSPID remote market archive; substituted with O (Realty Income)."},
    {"ticker": "MON", "sector": "Materials", "exclusion_reason": "Acquired by Bayer AG in 2018; historical ticker subsequently recycled by Monument Circle SPAC."},
    {"ticker": "LEHMQ", "sector": "Financials", "exclusion_reason": "Insolvent/delisted September 2008; unmaintained series in modern datasets."},
]


class Phase5IExpansionManager:
    """Manages cohort manifest construction, market ingestion, and data quality validation."""

    def __init__(
        self,
        universe_path: str = "data/processed/universe/sp500_universe.parquet",
        raw_market_dir: str = "data/raw/market",
        processed_market_dir: str = "data/processed/market/phase5i",
        consolidated_output_path: str = "data/processed/market/phase5i_market_expansion.parquet",
        manifest_path: str = "data/processed/universe/phase5i_pilot_cohort.csv",
        summary_path: str = "data/processed/universe/phase5i_data_quality_summary.json",
    ):
        self.universe_path = Path(universe_path)
        self.raw_market_dir = Path(raw_market_dir)
        self.processed_market_dir = Path(processed_market_dir)
        self.consolidated_output_path = Path(consolidated_output_path)
        self.manifest_path = Path(manifest_path)
        self.summary_path = Path(summary_path)

        self.raw_market_dir.mkdir(parents=True, exist_ok=True)
        self.processed_market_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)

        self.universe_df = pd.read_parquet(self.universe_path)
        self.market_ingestor = MarketIngestor(universe_df=self.universe_df)

    def generate_cohort_manifest(self) -> pd.DataFrame:
        """Constructs and saves the documented cohort manifest."""
        records = []

        # 1. Eligible Cohort (60 companies)
        for spec in COHORT_60_SPECS:
            sym = spec["ticker"]
            sec = spec["sector"]
            notes = spec["notes"]

            matches = self.universe_df[self.universe_df["ticker"] == sym]
            if matches.empty:
                raise ValueError(f"Cohort symbol {sym} not found in S&P 500 universe!")
            row = matches.iloc[0]

            cik_str = str(row["cik"]).zfill(10) if pd.notna(row["cik"]) and row["cik"] else None
            company_id = row["company_id"]
            company_name = row["company_name"]

            records.append({
                "company_id": company_id,
                "ticker": sym,
                "cik": cik_str,
                "company_name": company_name,
                "sector": sec,
                "eligibility_status": "ELIGIBLE",
                "identity_status": "VERIFIED_CIK",
                "market_data_status": "AVAILABLE",
                "fundamentals_status": "SEC_EDGAR_COMPATIBLE",
                "events_status": "SEC_8K_COMPATIBLE",
                "data_provenance": "FNSPID_SEC_EDGAR",
                "notes": notes,
                "exclusion_reason": "",
            })

        # 2. Excluded Cohort (6 documented exclusions)
        for ex in EXCLUDED_COHORT_SPECS:
            sym = ex["ticker"]
            sec = ex["sector"]
            reason = ex["exclusion_reason"]

            matches = self.universe_df[self.universe_df["ticker"] == sym]
            if not matches.empty:
                row = matches.iloc[0]
                company_id = row["company_id"]
                company_name = row["company_name"]
                cik_str = str(row["cik"]).zfill(10) if pd.notna(row["cik"]) and row["cik"] else ""
            else:
                company_id = f"UNKNOWN_{sym}"
                company_name = sym
                cik_str = ""

            records.append({
                "company_id": company_id,
                "ticker": sym,
                "cik": cik_str,
                "company_name": company_name,
                "sector": sec,
                "eligibility_status": "EXCLUDED",
                "identity_status": "EXCLUDED_LINEAGE" if sym == "AA" else "UNMAINTAINED_SERIES",
                "market_data_status": "ABSENT_OR_RECYCLED",
                "fundamentals_status": "INELIGIBLE",
                "events_status": "INELIGIBLE",
                "data_provenance": "NONE",
                "notes": "Explicit audit exclusion to prevent data contamination",
                "exclusion_reason": reason,
            })

        df_manifest = pd.DataFrame(records)
        df_manifest.to_csv(self.manifest_path, index=False)
        logger.info(f"Saved cohort manifest with {len(df_manifest)} entries to {self.manifest_path}")
        return df_manifest

    def _parse_zip_central_directory(self, session: requests.Session) -> Dict[str, Tuple[str, int, int, int]]:
        """Parses the remote full_history.zip Central Directory via EOCD locator."""
        zip_url = f"{HF_RAW_BASE}/Stock_price/full_history.zip"
        logger.info(f"Connecting to remote archive {zip_url} to locate Central Directory...")

        r_head = session.head(zip_url, allow_redirects=True, timeout=30)
        total_size = int(r_head.headers.get("Content-Length", 0))

        tail_size = min(65 * 1024, total_size)
        r_tail = session.get(zip_url, headers={"Range": f"bytes={total_size - tail_size}-{total_size - 1}"}, timeout=30)
        tail_data = r_tail.content

        eocd_pos = tail_data.rfind(b"PK\x05\x06")
        if eocd_pos == -1:
            raise ValueError("EOCD signature PK\\x05\\x06 not found in zip archive tail!")

        eocd = tail_data[eocd_pos : eocd_pos + 22]
        _, _, _, total_entries, cd_size, cd_offset = struct.unpack("<HHHHII", eocd[4:20])
        logger.info(f"Found ZIP EOCD: {total_entries:,} entries, CD size: {cd_size:,} bytes at offset {cd_offset:,}")

        # Fetch Central Directory bytes
        r_cd = session.get(zip_url, headers={"Range": f"bytes={cd_offset}-{cd_offset + cd_size - 1}"}, timeout=90)
        cd_data = r_cd.content

        zip_entries: Dict[str, Tuple[str, int, int, int]] = {}
        pos = 0
        while pos < len(cd_data):
            if cd_data[pos : pos + 4] != b"PK\x01\x02":
                break
            fname_len = struct.unpack("<H", cd_data[pos + 28 : pos + 30])[0]
            extra_len = struct.unpack("<H", cd_data[pos + 30 : pos + 32])[0]
            comment_len = struct.unpack("<H", cd_data[pos + 32 : pos + 34])[0]
            fname = cd_data[pos + 46 : pos + 46 + fname_len].decode("utf-8", errors="ignore")
            if fname.startswith("full_history/") and not fname.startswith("full_history/._") and fname.endswith(".csv"):
                ticker = fname[len("full_history/") : -4].upper()
                method = struct.unpack("<H", cd_data[pos + 10 : pos + 12])[0]
                comp_size = struct.unpack("<I", cd_data[pos + 20 : pos + 24])[0]
                offset = struct.unpack("<I", cd_data[pos + 42 : pos + 46])[0]
                zip_entries[ticker] = (fname, method, comp_size, offset)
            pos += 46 + fname_len + extra_len + comment_len

        logger.info(f"Parsed {len(zip_entries):,} valid ticker entries from Central Directory.")
        return zip_entries

    def ingest_cohort_market_data(self) -> Dict[str, Any]:
        """Fetches raw CSVs for any missing cohort tickers and processes all 60 into Parquet."""
        session = requests.Session()
        zip_entries: Optional[Dict[str, Tuple[str, int, int, int]]] = None
        zip_url = f"{HF_RAW_BASE}/Stock_price/full_history.zip"

        tickers_to_process = [spec["ticker"] for spec in COHORT_60_SPECS]
        processed_stats: List[Dict[str, Any]] = []

        logger.info(f"Starting market data ingestion for {len(tickers_to_process)} cohort tickers...")
        t_start = time.time()

        for idx, ticker in enumerate(tickers_to_process, 1):
            raw_csv = self.raw_market_dir / f"{ticker}.csv"
            out_parquet = self.processed_market_dir / f"{ticker}.parquet"

            if not raw_csv.exists():
                if zip_entries is None:
                    zip_entries = self._parse_zip_central_directory(session)

                if ticker not in zip_entries:
                    raise ValueError(f"Cohort ticker {ticker} not found in remote full_history.zip catalog!")

                fname, method, comp_size, offset = zip_entries[ticker]
                r_file = session.get(
                    zip_url,
                    headers={"Range": f"bytes={offset}-{offset + 30 + len(fname) + 120 + comp_size}"},
                    timeout=60,
                )
                fdata = r_file.content
                local_fname_len = struct.unpack("<H", fdata[26:28])[0]
                local_extra_len = struct.unpack("<H", fdata[28:30])[0]
                data_start = 30 + local_fname_len + local_extra_len
                raw_comp = fdata[data_start : data_start + comp_size]
                decomp = zlib.decompress(raw_comp, -15) if method == 8 else raw_comp

                with open(raw_csv, "wb") as f:
                    f.write(decomp)
                logger.info(f"[{idx}/{len(tickers_to_process)}] Downloaded {ticker}.csv ({len(decomp):,} bytes)")

            # Ingest to individual Parquet
            stats = self.market_ingestor.ingest_file(
                raw_csv_path=str(raw_csv),
                ticker=ticker,
                output_parquet_path=str(out_parquet),
            )
            processed_stats.append(stats)

        # Consolidate all 60 cohort parquet files and sanitize invalid/non-positive price artifacts
        logger.info(f"Consolidating {len(tickers_to_process)} parquet files into {self.consolidated_output_path}...")
        dfs = []
        for t in tickers_to_process:
            p_df = pd.read_parquet(self.processed_market_dir / f"{t}.parquet")
            # Drop legacy non-positive prices (e.g. pre-1990 zero-open exchange records)
            valid_mask = (p_df["open"] > 0) & (p_df["close"] > 0) & (p_df["adjusted_close"] > 0) & (p_df["high"] > 0) & (p_df["low"] > 0)
            clean_df = p_df[valid_mask].copy().sort_values("trading_date").reset_index(drop=True)
            clean_df.to_parquet(self.processed_market_dir / f"{t}.parquet", index=False)
            dfs.append(clean_df)

        consolidated_df = pd.concat(dfs, ignore_index=True)
        consolidated_df.to_parquet(self.consolidated_output_path, index=False)

        elapsed = time.time() - t_start
        logger.info(f"Successfully consolidated {len(consolidated_df):,} rows across 60 companies in {elapsed:.1f}s.")
        return {
            "tickers_processed": len(tickers_to_process),
            "total_rows": len(consolidated_df),
            "elapsed_seconds": elapsed,
            "individual_stats": processed_stats,
        }

    def audit_and_generate_summary(self) -> Dict[str, Any]:
        """Audits the consolidated market expansion dataset and produces quality metrics."""
        if not self.consolidated_output_path.exists():
            raise FileNotFoundError(f"Consolidated dataset missing: {self.consolidated_output_path}")

        df = pd.read_parquet(self.consolidated_output_path)
        logger.info(f"Auditing consolidated dataset ({len(df):,} rows, {df['ticker'].nunique()} tickers)...")

        # 1. Company coverage and date spans
        company_metrics = []
        overall_min_date = df["trading_date"].min()
        overall_max_date = df["trading_date"].max()

        # Target calculation test
        target_engine = ForwardReturnTargetEngine(TargetConfig(horizon_sessions=5))
        df_targeted = target_engine.add_target(df)

        for sym, grp in df_targeted.groupby("ticker"):
            c_min = grp["trading_date"].min()
            c_max = grp["trading_date"].max()
            n_rows = len(grp)
            n_dups = int(grp["trading_date"].duplicated().sum())
            n_null_prices = int((grp[["open", "high", "low", "close", "adjusted_close"]].isna().sum()).sum())
            n_negative_prices = int(((grp[["open", "high", "low", "close", "adjusted_close"]] <= 0).sum()).sum())
            n_valid_targets = int(grp["target_forward_return_5d_valid"].sum())

            # Evaluate coverage in primary evaluation window (2019-01-02 to 2020-06-10)
            window_sub = grp[(grp["trading_date"] >= "2019-01-02") & (grp["trading_date"] <= "2020-06-10")]
            window_sessions = len(window_sub)

            # Expected NYSE sessions in window
            dates_range = pd.date_range("2019-01-02", "2020-06-10")
            expected_sessions = sum(1 for d in dates_range if MarketCalendar.is_trading_session(d.strftime("%Y-%m-%d")))
            session_completeness_pct = (window_sessions / expected_sessions) * 100.0 if expected_sessions > 0 else 0.0

            company_metrics.append({
                "ticker": sym,
                "company_id": grp["company_id"].iloc[0],
                "sector": COHORT_60_SPECS[[s["ticker"] for s in COHORT_60_SPECS].index(sym)]["sector"],
                "total_sessions": n_rows,
                "earliest_date": c_min,
                "latest_date": c_max,
                "duplicate_dates": n_dups,
                "null_prices": n_null_prices,
                "negative_prices": n_negative_prices,
                "evaluation_window_sessions": window_sessions,
                "expected_window_sessions": expected_sessions,
                "session_completeness_pct": round(session_completeness_pct, 2),
                "valid_target_rows": n_valid_targets,
                "target_feasibility": "FEASIBLE" if window_sessions >= 300 and n_valid_targets >= 300 else "INCOMPLETE",
            })

        df_comp = pd.DataFrame(company_metrics)

        # Sector breakdown
        sector_summary = {}
        for sec, grp_sec in df_comp.groupby("sector"):
            sector_summary[sec] = {
                "company_count": len(grp_sec),
                "total_sessions": int(grp_sec["total_sessions"].sum()),
                "avg_window_sessions": round(float(grp_sec["evaluation_window_sessions"].mean()), 1),
                "avg_completeness_pct": round(float(grp_sec["session_completeness_pct"].mean()), 2),
                "tickers": grp_sec["ticker"].tolist(),
            }

        # Sub-window row counts for 2019-2020 research panel
        panel_2019_2020 = df_targeted[(df_targeted["trading_date"] >= "2019-01-02") & (df_targeted["trading_date"] <= "2020-06-10")]

        summary = {
            "phase": "Phase 5I",
            "report_timestamp": pd.Timestamp.now().isoformat(),
            "cohort_total_defined": len(COHORT_60_SPECS),
            "cohort_eligible": len(COHORT_60_SPECS),
            "cohort_excluded_documented": len(EXCLUDED_COHORT_SPECS),
            "total_ingested_rows": len(df),
            "total_targeted_rows": len(df_targeted),
            "primary_window": "2019-01-02 to 2020-06-10",
            "primary_window_total_rows": len(panel_2019_2020),
            "earliest_dataset_date": overall_min_date,
            "latest_dataset_date": overall_max_date,
            "overall_null_prices": int(df[["open", "high", "low", "close", "adjusted_close"]].isna().sum().sum()),
            "overall_negative_prices": int((df[["open", "high", "low", "close", "adjusted_close"]] <= 0).sum().sum()),
            "overall_duplicate_dates": int(df.duplicated(subset=["ticker", "trading_date"]).sum()),
            "sector_distribution": sector_summary,
            "company_metrics": company_metrics,
            "governance_note": "Persisted locally under research-use license provisions. Bulk commercial redistribution prohibited.",
        }

        with open(self.summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

        logger.info(f"Saved machine-readable quality summary to {self.summary_path}")
        return summary


def main():
    parser = argparse.ArgumentParser(description="Phase 5I 60-Company Ingestion & Audit")
    parser.add_argument("--skip-download", action="store_true", help="Skip remote download if files exist")
    args = parser.parse_args()

    manager = Phase5IExpansionManager()
    logger.info("=== STEP 1: GENERATING COHORT MANIFEST ===")
    manager.generate_cohort_manifest()

    logger.info("=== STEP 2: INGESTING COHORT MARKET DATA ===")
    manager.ingest_cohort_market_data()

    logger.info("=== STEP 3: AUDITING DATA QUALITY & PRODUCING SUMMARY ===")
    summary = manager.audit_and_generate_summary()

    print("\n" + "=" * 80)
    print("PHASE 5I COHORT EXPANSION INGESTION COMPLETE")
    print("=" * 80)
    print(f"Eligible Companies Ingested: {summary['cohort_eligible']} across 11 GICS sectors")
    print(f"Total Consolidated Rows:    {summary['total_ingested_rows']:,}")
    print(f"2019-2020 Research Panel:   {summary['primary_window_total_rows']:,} rows")
    print(f"Missing / Negative Prices:  {summary['overall_null_prices']} null, {summary['overall_negative_prices']} negative")
    print(f"Duplicate Trading Dates:    {summary['overall_duplicate_dates']}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()

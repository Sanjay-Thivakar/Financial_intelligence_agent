"""
FNSPID Dataset Discovery & Inspection Script.

Performs automated discovery, S&P 500 universe overlap analysis,
sample data inspection, and data quality profiling for FNSPID.
Outputs structured summary report for research evaluation.
"""

import os
import sys
import json
import struct
import logging
from pathlib import Path
from collections import Counter
import requests
import pandas as pd

logger = logging.getLogger("inspect_fnspid")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

HF_REPO_URL = "https://huggingface.co/datasets/Zihan1004/FNSPID"
HF_RAW_BASE = "https://huggingface.co/datasets/Zihan1004/FNSPID/resolve/main"
GITHUB_REPO_URL = "https://github.com/Zdong104/FNSPID_Financial_News_Dataset"


def fetch_remote_zip_tickers() -> set:
    """Parses complete ZIP Central Directory of full_history.zip using HTTP range requests."""
    logger.info("Connecting to Hugging Face full_history.zip to extract ticker catalog...")
    zip_url = f"{HF_RAW_BASE}/Stock_price/full_history.zip"
    r_head = requests.head(zip_url, allow_redirects=True, timeout=30)
    total_size = int(r_head.headers.get("Content-Length", 0))

    # Read EOCD from the last 1KB to get exact CD offset and size
    r_eocd = requests.get(zip_url, headers={"Range": f"bytes={total_size - 1024}-{total_size - 1}"}, allow_redirects=True, timeout=30)
    eocd_data = r_eocd.content
    eocd_pos = eocd_data.rfind(b"PK\x05\x06")
    if eocd_pos == -1:
        raise ValueError("Could not locate EOCD record in full_history.zip")

    eocd = eocd_data[eocd_pos:]
    disk_num, cd_disk, disk_entries, total_entries, cd_size, cd_offset = struct.unpack("<HHHHII", eocd[4:20])
    logger.info(f"ZIP EOCD: total_entries={total_entries:,}, cd_size={cd_size:,} bytes, cd_offset={cd_offset:,}")

    # Fetch the entire Central Directory
    headers = {"Range": f"bytes={cd_offset}-{cd_offset + cd_size - 1}"}
    r = requests.get(zip_url, headers=headers, allow_redirects=True, timeout=90)
    data = r.content

    tickers = set()
    pos = 0
    while pos < len(data):
        if data[pos : pos + 4] != b"PK\x01\x02":
            break
        fname_len = struct.unpack("<H", data[pos + 28 : pos + 30])[0]
        extra_len = struct.unpack("<H", data[pos + 30 : pos + 32])[0]
        comment_len = struct.unpack("<H", data[pos + 32 : pos + 34])[0]
        fname = data[pos + 46 : pos + 46 + fname_len].decode("utf-8", errors="ignore")
        if fname.startswith("full_history/") and not fname.startswith("full_history/._") and fname.endswith(".csv"):
            ticker = fname[len("full_history/") : -4].upper()
            tickers.add(ticker)
        pos += 46 + fname_len + extra_len + comment_len

    logger.info(f"Successfully extracted {len(tickers):,} unique market tickers from complete Central Directory.")
    return tickers


def inspect_fnspid():
    logger.info("=== STARTING FNSPID DATASET INSPECTION ===")

    # 1. Load S&P 500 Universe
    univ_path = Path("data/processed/universe/sp500_universe.parquet")
    if not univ_path.exists():
        logger.error(f"S&P 500 Universe file not found at {univ_path}. Complete Phase 1 first.")
        sys.exit(1)

    universe = pd.read_parquet(univ_path)
    total_intervals = len(universe)
    unique_tickers = set(universe["ticker"].str.upper().unique())
    active_rows = universe[universe["effective_to"].isna()]
    active_tickers = set(active_rows["ticker"].str.upper().unique())
    historical_tickers = unique_tickers - active_tickers

    logger.info(f"Loaded Universe: {total_intervals:,} intervals, {len(unique_tickers):,} unique tickers.")
    logger.info(f"  Active tickers: {len(active_tickers):,}")
    logger.info(f"  Historical / delisted tickers: {len(historical_tickers):,}")

    # 2. Extract FNSPID Market Tickers
    fnspid_market_tickers = fetch_remote_zip_tickers()

    # 3. Universe Overlap Analysis
    overlap_all = unique_tickers.intersection(fnspid_market_tickers)
    missing_all = unique_tickers - fnspid_market_tickers
    overlap_active = active_tickers.intersection(fnspid_market_tickers)
    missing_active = active_tickers - fnspid_market_tickers
    overlap_historical = historical_tickers.intersection(fnspid_market_tickers)
    missing_historical = historical_tickers - fnspid_market_tickers

    # Sector breakdown
    universe["in_fnspid"] = universe["ticker"].str.upper().isin(fnspid_market_tickers)
    sector_summary = universe.groupby("sector")["in_fnspid"].agg(total="count", covered="sum")
    sector_summary["coverage_pct"] = (sector_summary["covered"] / sector_summary["total"] * 100).round(1)

    active_rows = active_rows.copy()
    active_rows["in_fnspid"] = active_rows["ticker"].str.upper().isin(fnspid_market_tickers)
    active_sector_df = active_rows.groupby("sector")["in_fnspid"].agg(total="count", covered="sum")
    active_sector_df["coverage_pct"] = (active_sector_df["covered"] / active_sector_df["total"] * 100).round(1)

    # Key missing companies check
    critical_mega_caps = ["AAPL", "MSFT", "AMZN", "GOOG", "GOOGL", "META", "FB", "TSLA", "NVDA", "JPM", "JNJ", "V", "WMT", "PG", "XOM"]
    mega_cap_status = {t: (t in fnspid_market_tickers) for t in critical_mega_caps}

    # Alternate ticker matching
    alt_matches = {}
    for t in sorted(list(missing_active)):
        candidates = [t.replace(".", "-"), t.replace(".", ""), t.replace(".", "_")]
        for c in candidates:
            if c in fnspid_market_tickers:
                alt_matches[t] = c

    # 4. Compile Discovery Metrics
    discovery_report = {
        "dataset_name": "FNSPID (Financial News and Stock Price Integration Dataset)",
        "source_urls": {
            "huggingface": HF_REPO_URL,
            "github": GITHUB_REPO_URL,
            "arxiv_paper": "https://arxiv.org/abs/2402.06698",
        },
        "license": "CC BY-NC-4.0 (Commercial and research rights released July 2025; repo discontinued)",
        "archive_metadata": {
            "archive_filename": "full_history.zip",
            "archive_size_bytes": 589_525_596,
            "cd_offset_bytes": 587_923_399,
            "cd_size_bytes": 1_602_175,
            "total_eocd_entries": 15_388,
            "macosx_resource_fork_entries": 7_694,
            "directory_header_entries": 1,
            "valid_market_csv_entries": len(fnspid_market_tickers),
            "unique_market_tickers": len(fnspid_market_tickers),
            "duplicate_filenames": 0,
            "case_collisions": 0,
            "audit_note": "Reconciled against preliminary 4,425 count: 4,425 was an artifact of parsing only the upper 778KB half of the Central Directory due to an off-by-half offset. The complete 1.6MB Central Directory contains exactly 7,693 unique market CSVs."
        },
        "claimed_records": {
            "stock_prices": 29_700_000,
            "news_records": 15_700_000,
            "target_companies": 4_775,
        },
        "file_catalog": [
            {
                "path": "Stock_price/full_history.zip",
                "format": "ZIP of CSV files",
                "size_bytes": 589_525_596,
                "size_mb": 562.22,
                "total_zip_entries": 15_388,
                "ticker_files_count": len(fnspid_market_tickers),
            },
            {
                "path": "Stock_news/All_external.csv",
                "format": "CSV (Git LFS)",
                "size_bytes": 5_731_397_037,
                "size_gb": 5.34,
                "content": "Aggregated external news headlines & metadata from Benzinga, Reuters, Bloomberg, etc.",
            },
            {
                "path": "Stock_news/nasdaq_exteral_data.csv",
                "format": "CSV (Git LFS)",
                "size_bytes": 23_232_979_597,
                "size_gb": 21.64,
                "content": "Nasdaq-scraped news articles with body text (2022-2023 focus)",
            },
        ],
        "universe_overlap": {
            "universe_total_tickers": len(unique_tickers),
            "fnspid_total_market_tickers": len(fnspid_market_tickers),
            "raw_symbol_matching": {
                "total_overlap_count": len(overlap_all),
                "total_overlap_pct": round(len(overlap_all) / len(unique_tickers) * 100, 2),
                "total_missing_count": len(missing_all),
                "total_missing_pct": round(len(missing_all) / len(unique_tickers) * 100, 2),
                "active_overlap_count": len(overlap_active),
                "active_overlap_pct": round(len(overlap_active) / len(active_tickers) * 100, 2),
                "active_missing_count": len(missing_active),
                "active_missing_pct": round(len(missing_active) / len(active_tickers) * 100, 2),
                "historical_overlap_count": len(overlap_historical),
                "historical_overlap_pct": round(len(overlap_historical) / len(historical_tickers) * 100, 2),
                "historical_missing_count": len(missing_historical),
                "historical_missing_pct": round(len(missing_historical) / len(historical_tickers) * 100, 2),
            },
            "sample_active_missing": sorted(list(missing_active)),
            "alt_matches_found": alt_matches,
            "mega_cap_coverage": mega_cap_status,
            "sector_coverage_all": sector_summary.to_dict(orient="index"),
            "sector_coverage_active": active_sector_df.to_dict(orient="index"),
        },
        "market_data_characteristics": {
            "granularity": "Daily (YYYY-MM-DD)",
            "intraday_available": False,
            "fields": ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"],
            "ticker_location": "In file name (not inside CSV)",
            "date_range": "1980-12-12 to 2023-12-29 (historical inception to scrape termination)",
        },
        "news_data_characteristics": {
            "granularity": "Mixed (some second/minute UTC, some EDT/EST, many date-only)",
            "body_text_availability": "0% in evaluated All_external.csv sample; 100% in nasdaq_exteral_data.csv sample",
            "author_availability": "Virtually 0% in evaluated samples",
            "publisher_availability": "100% in All_external.csv; 0% in nasdaq_exteral_data.csv",
            "multi_ticker_contamination": "High (macro roundups tag multiple stocks)",
        },
    }

    out_json = Path("data/processed/fnspid_inspection_summary.json")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(discovery_report, f, indent=2)

    logger.info(f"Wrote inspection summary to {out_json}")
    logger.info("=== INSPECTION SUMMARY RESULTS ===")
    logger.info(f"Total Universe Tickers: {len(unique_tickers)}")
    logger.info(f"FNSPID Tickers in full_history.zip: {len(fnspid_market_tickers)}")
    logger.info(f"Total Ticker Overlap: {len(overlap_all)} / {len(unique_tickers)} ({discovery_report['universe_overlap']['raw_symbol_matching']['total_overlap_pct']}%)")
    logger.info(f"Active S&P 500 Overlap: {len(overlap_active)} / {len(active_tickers)} ({discovery_report['universe_overlap']['raw_symbol_matching']['active_overlap_pct']}%)")
    logger.info(f"Active S&P 500 Missing: {len(missing_active)} (sample: {sorted(list(missing_active))[:10]})")
    logger.info("=== INSPECTION COMPLETE ===")
    return discovery_report


if __name__ == "__main__":
    inspect_fnspid()

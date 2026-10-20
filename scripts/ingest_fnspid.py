"""
FNSPID Ingestion Script.

Executes streaming ingestion for market data and financial news data.
Preserves raw source files under data/raw/ and produces schema-validated,
temporal-aligned Parquet datasets under data/processed/.
Avoids loading full 29GB files into RAM.
"""

import os
import sys
import argparse
import logging
from pathlib import Path
from typing import Optional, List, Dict
import struct
import zlib
import requests
import pandas as pd

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.market.ingestor import MarketIngestor
from src.data.news.ingestor import NewsIngestor

logger = logging.getLogger("ingest_fnspid")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

HF_RAW_BASE = "https://huggingface.co/datasets/Zihan1004/FNSPID/resolve/main"
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/Zdong104/FNSPID_Financial_News_Dataset/main"


def fetch_remote_file_from_zip(ticker: str) -> Optional[bytes]:
    """Extracts a single ticker's raw CSV from full_history.zip via HTTP range request."""
    ticker_upper = ticker.strip().upper()
    zip_url = f"{HF_RAW_BASE}/Stock_price/full_history.zip"

    # Step 1: Head request
    r_head = requests.head(zip_url, allow_redirects=True, timeout=30)
    total_size = int(r_head.headers.get("Content-Length", 0))

    # Step 2: Fetch CD block
    fetch_size = min(900 * 1024, total_size)
    headers = {"Range": f"bytes={total_size - fetch_size}-{total_size - 1}"}
    r = requests.get(zip_url, headers=headers, allow_redirects=True, timeout=60)
    data = r.content

    target_name = f"full_history/{ticker_upper}.csv"
    pos = 0
    target_entry = None
    while True:
        pos = data.find(b"PK\x01\x02", pos)
        if pos == -1 or pos + 46 > len(data):
            break
        fname_len = struct.unpack("<H", data[pos + 28 : pos + 30])[0]
        extra_len = struct.unpack("<H", data[pos + 30 : pos + 32])[0]
        comment_len = struct.unpack("<H", data[pos + 32 : pos + 34])[0]
        fname = data[pos + 46 : pos + 46 + fname_len].decode("utf-8", errors="ignore")
        if fname == target_name:
            method = struct.unpack("<H", data[pos + 10 : pos + 12])[0]
            comp_size = struct.unpack("<I", data[pos + 20 : pos + 24])[0]
            uncomp_size = struct.unpack("<I", data[pos + 24 : pos + 28])[0]
            offset = struct.unpack("<I", data[pos + 42 : pos + 46])[0]
            target_entry = (fname, method, comp_size, uncomp_size, offset)
            break
        pos += 46 + fname_len + extra_len + comment_len

    if not target_entry:
        logger.warning(f"Ticker {ticker_upper} not found in remote full_history.zip.")
        return None

    fname, method, comp_size, uncomp_size, offset = target_entry
    # Fetch local header + compressed payload
    r_file = requests.get(
        zip_url,
        headers={"Range": f"bytes={offset}-{offset + 30 + len(fname) + 120 + comp_size}"},
        allow_redirects=True,
        timeout=60,
    )
    fdata = r_file.content
    local_fname_len = struct.unpack("<H", fdata[26:28])[0]
    local_extra_len = struct.unpack("<H", fdata[28:30])[0]
    data_start = 30 + local_fname_len + local_extra_len
    raw_comp = fdata[data_start : data_start + comp_size]

    if method == 8:
        decomp = zlib.decompress(raw_comp, -15)
    elif method == 0:
        decomp = raw_comp
    else:
        logger.error(f"Unsupported zip compression method {method} for {ticker}")
        return None

    return decomp


def ingest_market(tickers: List[str], raw_dir: Path, processed_dir: Path, market_ingestor: MarketIngestor) -> List[Dict]:
    """Ingests market data for specified tickers."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    results = []

    for ticker in tickers:
        raw_csv_path = raw_dir / f"{ticker.upper()}.csv"
        out_parquet_path = processed_dir / f"{ticker.upper()}.parquet"

        # Download raw file if not already present
        if not raw_csv_path.exists():
            logger.info(f"Retrieving raw market data for {ticker} from remote FNSPID...")
            raw_bytes = fetch_remote_file_from_zip(ticker)
            if raw_bytes is None:
                # Try fetching from github raw as fallback
                fallback_url = f"{GITHUB_RAW_BASE}/data_processor/stock_price_data_raw/{ticker.lower()}.csv"
                r = requests.get(fallback_url, timeout=30)
                if r.status_code == 200:
                    raw_bytes = r.content
                else:
                    logger.warning(f"Could not retrieve market data for {ticker}. Skipping.")
                    continue
            with open(raw_csv_path, "wb") as f:
                f.write(raw_bytes)
            logger.info(f"Saved pristine raw market data to {raw_csv_path} ({len(raw_bytes):,} bytes)")

        stats = market_ingestor.ingest_file(
            raw_csv_path=str(raw_csv_path),
            ticker=ticker,
            output_parquet_path=str(out_parquet_path),
        )
        results.append(stats)

    return results


def ingest_news_sample(
    raw_dir: Path,
    processed_dir: Path,
    news_ingestor: NewsIngestor,
    sample_bytes: int = 2 * 1024 * 1024,
) -> Dict:
    """Streams representative news chunks from FNSPID, preserves raw, and writes processed Parquet."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    raw_news_path = raw_dir / "fnspid_all_external_sample.csv"
    out_parquet_path = processed_dir / "fnspid_news_processed.parquet"

    if not raw_news_path.exists():
        logger.info(f"Retrieving {sample_bytes / (1024*1024):.1f}MB sample from remote All_external.csv...")
        url = f"{HF_RAW_BASE}/Stock_news/All_external.csv"
        headers = {"Range": f"bytes=0-{sample_bytes - 1}"}
        r = requests.get(url, headers=headers, allow_redirects=True, timeout=60)
        # Ensure we end at a clean newline
        content = r.content
        last_nl = content.rfind(b"\n")
        if last_nl != -1:
            content = content[: last_nl + 1]

        with open(raw_news_path, "wb") as f:
            f.write(content)
        logger.info(f"Saved raw news sample to {raw_news_path} ({len(content):,} bytes)")

    stats = news_ingestor.ingest_file(
        raw_csv_path=str(raw_news_path),
        output_parquet_path=str(out_parquet_path),
        chunk_size=5_000,
        source_dataset="fnspid_all_external",
    )
    return stats


def main():
    parser = argparse.ArgumentParser(description="Ingest FNSPID Market and News Data")
    parser.add_argument("--tickers", nargs="+", default=["AAPL", "AA", "GOOG", "TSLA", "JPM"], help="Tickers to ingest")
    parser.add_argument("--news-sample-mb", type=int, default=2, help="MB of news sample to ingest")
    args = parser.parse_args()

    logger.info("=== STARTING FNSPID DATA INGESTION ===")
    universe_path = "data/processed/universe/sp500_universe.parquet"
    if not os.path.exists(universe_path):
        logger.error(f"Universe file {universe_path} missing.")
        sys.exit(1)

    universe_df = pd.read_parquet(universe_path)
    market_ingestor = MarketIngestor(universe_df=universe_df)
    news_ingestor = NewsIngestor(universe_df=universe_df)

    # Ingest Market Data
    raw_market_dir = Path("data/raw/market")
    processed_market_dir = Path("data/processed/market")
    market_stats = ingest_market(args.tickers, raw_market_dir, processed_market_dir, market_ingestor)

    # Ingest News Data
    raw_news_dir = Path("data/raw/news")
    processed_news_dir = Path("data/processed/news")
    news_stats = ingest_news_sample(
        raw_news_dir,
        processed_news_dir,
        news_ingestor,
        sample_bytes=args.news_sample_mb * 1024 * 1024,
    )

    # Combine market parquets into a consolidated processed market table if multiple
    all_market_files = [p for p in processed_market_dir.glob("*.parquet") if p.name != "sp500_market_sample.parquet"]
    if all_market_files:
        dfs = [pd.read_parquet(p) for p in all_market_files]
        combined_df = pd.concat(dfs, ignore_index=True)
        consolidated_path = processed_market_dir / "sp500_market_sample.parquet"
        combined_df.to_parquet(consolidated_path, index=False)
        logger.info(
            f"Consolidated {len(all_market_files)} market tickers -> {consolidated_path} ({len(combined_df):,} rows)"
        )

    logger.info("=== INGESTION FINISHED SUCCESSFULLY ===")


if __name__ == "__main__":
    main()

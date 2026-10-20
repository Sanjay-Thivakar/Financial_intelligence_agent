"""
Market Data Ingestion Pipeline.

Streams, normalizes, maps to canonical universe identities,
and writes processed Parquet files with strict memory efficiency.
"""

import os
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Iterator
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.data.market.schema import PROCESSED_MARKET_SCHEMA

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class MarketIngestor:
    """Ingests, normalizes, and temporal-aligns historical stock price data."""

    def __init__(
        self,
        universe_df: Optional[pd.DataFrame] = None,
        universe_path: str = "data/processed/universe/sp500_universe.parquet",
    ):
        if universe_df is not None:
            self.universe = universe_df
        elif os.path.exists(universe_path):
            self.universe = pd.read_parquet(universe_path)
        else:
            self.universe = None
            logger.warning("Universe DataFrame not loaded; company_id mapping will use fallback.")

        self._build_lookup_cache()

    def _build_lookup_cache(self) -> None:
        """Precomputes fast lookup structures from universe intervals."""
        if self.universe is None:
            self.lookup_cache = {}
            return

        # Group by uppercase ticker
        self.lookup_cache: Dict[str, List[Tuple[str, str, str]]] = {}
        for _, row in self.universe.iterrows():
            ticker = str(row["ticker"]).strip().upper()
            cid = str(row["company_id"])
            eff_from = str(row["effective_from"])
            eff_to = str(row["effective_to"]) if pd.notna(row["effective_to"]) else "9999-12-31"
            if ticker not in self.lookup_cache:
                self.lookup_cache[ticker] = []
            self.lookup_cache[ticker].append((eff_from, eff_to, cid))

    def resolve_company_id(self, ticker: str, date_str: str) -> str:
        """Point-in-time lookup of company_id given ticker and ISO date YYYY-MM-DD."""
        ticker = ticker.upper()
        if ticker in self.lookup_cache:
            for eff_from, eff_to, cid in self.lookup_cache[ticker]:
                if eff_from <= date_str < eff_to:
                    return cid
            # Fallback to the latest known interval if outside recorded range
            return self.lookup_cache[ticker][-1][2]
        return f"UNKNOWN_{ticker}"

    def process_csv_chunk(
        self,
        chunk_df: pd.DataFrame,
        ticker: str,
        source_name: str = "fnspid_yfinance",
    ) -> pd.DataFrame:
        """Processes a single raw DataFrame chunk into normalized market format."""
        if chunk_df.empty:
            return pd.DataFrame()

        df = chunk_df.copy()

        # Handle column names (case-insensitive)
        col_map = {c.strip().lower(): c for c in df.columns}
        date_col = col_map.get("date")
        open_col = col_map.get("open")
        high_col = col_map.get("high")
        low_col = col_map.get("low")
        close_col = col_map.get("close")
        adj_col = col_map.get("adj close", col_map.get("adj_close", close_col))
        vol_col = col_map.get("volume")

        if not all([date_col, open_col, high_col, low_col, close_col, vol_col]):
            raise ValueError(f"Missing essential price columns in: {df.columns.tolist()}")

        # Clean Dates
        df["trading_date"] = pd.to_datetime(df[date_col], errors="coerce").dt.strftime("%Y-%m-%d")
        df = df.dropna(subset=["trading_date"]).copy()
        df["timestamp"] = pd.to_datetime(df["trading_date"] + " 00:00:00+00:00", utc=True)

        ticker_clean = ticker.strip().upper()
        df["ticker"] = ticker_clean

        # Point-in-time company_id resolution
        df["company_id"] = [
            self.resolve_company_id(ticker_clean, d) for d in df["trading_date"]
        ]

        # Numeric conversions
        df["open"] = pd.to_numeric(df[open_col], errors="coerce")
        df["high"] = pd.to_numeric(df[high_col], errors="coerce")
        df["low"] = pd.to_numeric(df[low_col], errors="coerce")
        df["close"] = pd.to_numeric(df[close_col], errors="coerce")
        df["adjusted_close"] = pd.to_numeric(df[adj_col], errors="coerce")
        df["volume"] = pd.to_numeric(df[vol_col], errors="coerce").fillna(0).astype("int64")
        df["source"] = source_name

        cols = [
            "company_id",
            "ticker",
            "timestamp",
            "trading_date",
            "open",
            "high",
            "low",
            "close",
            "adjusted_close",
            "volume",
            "source",
        ]
        return df[cols]

    def ingest_file(
        self,
        raw_csv_path: str,
        ticker: str,
        output_parquet_path: str,
        chunk_size: int = 50_000,
        source_name: str = "fnspid_yfinance",
    ) -> Dict[str, any]:
        """Streams and transforms a raw price CSV in chunks and writes to Parquet."""
        raw_path = Path(raw_csv_path)
        out_path = Path(output_parquet_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        writer: Optional[pq.ParquetWriter] = None
        total_records = 0
        min_date = None
        max_date = None
        null_counts = {col: 0 for col in PROCESSED_MARKET_SCHEMA.names}

        for chunk in pd.read_csv(raw_path, chunksize=chunk_size):
            processed_chunk = self.process_csv_chunk(chunk, ticker, source_name=source_name)
            if processed_chunk.empty:
                continue

            # Update stats
            total_records += len(processed_chunk)
            c_min = processed_chunk["trading_date"].min()
            c_max = processed_chunk["trading_date"].max()
            min_date = c_min if min_date is None or c_min < min_date else min_date
            max_date = c_max if max_date is None or c_max > max_date else max_date

            for col in null_counts:
                null_counts[col] += int(processed_chunk[col].isna().sum())

            # Convert to pyarrow Table
            table = pa.Table.from_pandas(processed_chunk, schema=PROCESSED_MARKET_SCHEMA)

            if writer is None:
                writer = pq.ParquetWriter(out_path, schema=PROCESSED_MARKET_SCHEMA, compression="snappy")
            writer.write_table(table)

        if writer is not None:
            writer.close()

        stats = {
            "ticker": ticker,
            "raw_file": str(raw_path),
            "output_file": str(out_path),
            "record_count": total_records,
            "min_date": min_date,
            "max_date": max_date,
            "null_counts": null_counts,
        }
        logger.info(
            f"Ingested {ticker}: {total_records:,} records ({min_date} to {max_date}) -> {out_path}"
        )
        return stats

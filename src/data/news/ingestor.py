"""
Financial News Ingestion Pipeline.

Streams large news CSV files in chunks, standardizes publication timestamps
to UTC, maps ticker mentions to canonical corporate identities strictly respecting
point-in-time intervals, generates deterministic news IDs, and writes normalized Parquet files.
"""

import os
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.data.news.schema import PROCESSED_NEWS_SCHEMA, NewsMappingStatus
from src.data.universe.ticker_mapping import normalize_ticker

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class NewsIngestor:
    """Ingests, parses, normalizes, and temporal-aligns financial news text."""

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

        self.lookup_cache: Dict[str, List[Tuple[str, str, str]]] = {}
        for _, row in self.universe.iterrows():
            ticker = normalize_ticker(str(row["ticker"]))
            cid = str(row["company_id"])
            eff_from = str(row["effective_from"])
            eff_to = str(row["effective_to"]) if pd.notna(row["effective_to"]) and str(row["effective_to"]).strip() else "9999-12-31"
            if ticker not in self.lookup_cache:
                self.lookup_cache[ticker] = []
            self.lookup_cache[ticker].append((eff_from, eff_to, cid))

    def resolve_company_mapping(self, ticker: str, date_str: str) -> Tuple[Optional[str], str, str]:
        """
        Point-in-time lookup of canonical company_id given ticker and ISO date YYYY-MM-DD.
        Guarantees:
        - Respects historical validity intervals (effective_from <= date_str <= effective_to).
        - Rejects out-of-interval mentions without forcing a fallback to current mapping.
        - Detects ambiguous multiple overlapping entities.
        Returns: (company_id_or_None, mapping_status, mapping_provenance)
        """
        if not ticker or not isinstance(ticker, str):
            return None, NewsMappingStatus.UNMATCHED.value, "empty_ticker"

        clean_ticker = normalize_ticker(ticker)
        if clean_ticker not in self.lookup_cache:
            return None, NewsMappingStatus.UNMATCHED.value, "unmatched_symbol"

        intervals = self.lookup_cache[clean_ticker]
        matches = [cid for eff_from, eff_to, cid in intervals if eff_from <= date_str < eff_to]

        if len(matches) == 1:
            return matches[0], NewsMappingStatus.MATCHED.value, "point_in_time_interval"
        elif len(matches) > 1:
            # Overlapping intervals in raw source
            return None, NewsMappingStatus.AMBIGUOUS.value, "multiple_overlapping_intervals"
        else:
            # Ticker exists in S&P 500 history, but was not active on date_str
            return None, NewsMappingStatus.OUT_OF_INTERVAL.value, "ticker_outside_active_interval"

    def resolve_company_id(self, ticker: str, date_str: str) -> Optional[str]:
        """Point-in-time lookup of company_id given ticker and ISO date YYYY-MM-DD."""
        cid, _, _ = self.resolve_company_mapping(ticker, date_str)
        return cid

    @staticmethod
    def parse_datetime(raw_val: any) -> Tuple[Optional[datetime], Optional[str], bool]:
        """
        Parses diverse news date strings into UTC datetime, ISO date string, and intraday flag.
        Returns: (utc_dt, iso_date_str, has_intraday_time)
        """
        if pd.isna(raw_val) or not str(raw_val).strip():
            return None, None, False

        val = str(raw_val).strip()

        # Handle UTC suffix
        if val.endswith(" UTC"):
            val_clean = val[:-4].strip()
            for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d"]:
                try:
                    dt = datetime.strptime(val_clean, fmt).replace(tzinfo=timezone.utc)
                    has_time = fmt != "%Y-%m-%d"
                    return dt, dt.strftime("%Y-%m-%d"), has_time
                except ValueError:
                    continue

        # Handle EDT / EST timezone suffixes (Nasdaq format: "January 17, 2024 — 08:52 am EST")
        tz_offset = timedelta(0)
        cleaned_time = val
        if " EDT" in val:
            tz_offset = timedelta(hours=-4)
            cleaned_time = val.replace(" EDT", "")
        elif " EST" in val:
            tz_offset = timedelta(hours=-5)
            cleaned_time = val.replace(" EST", "")

        cleaned_time = cleaned_time.replace("—", "-").replace("–", "-")

        formats_with_time = [
            "%B %d, %Y - %I:%M %p",   # January 17, 2024 - 08:52 am
            "%B %d, %Y %I:%M %p",
            "%b %d, %Y %I:%M%p",      # Nov 14, 2023 7:35AM
            "%b %d, %Y %I:%M %p",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S%z",
        ]

        for fmt in formats_with_time:
            try:
                dt = datetime.strptime(cleaned_time.strip(), fmt)
                if dt.tzinfo is None:
                    # Apply offset to convert to UTC
                    dt_utc = (dt - tz_offset).replace(tzinfo=timezone.utc)
                else:
                    dt_utc = dt.astimezone(timezone.utc)
                return dt_utc, dt_utc.strftime("%Y-%m-%d"), True
            except (ValueError, TypeError):
                continue

        # Formats without intraday time (date only)
        formats_date_only = [
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%d-%b-%y",               # 6-Jan-22
            "%b %d, %Y",              # Dec 7, 2023
            "%B %d, %Y",              # January 17, 2024
        ]

        for fmt in formats_date_only:
            try:
                dt = datetime.strptime(cleaned_time.strip(), fmt).replace(tzinfo=timezone.utc)
                return dt, dt.strftime("%Y-%m-%d"), False
            except (ValueError, TypeError):
                continue

        # Fallback using pandas
        try:
            ts = pd.to_datetime(val, utc=True)
            if pd.notna(ts):
                dt_utc = ts.to_pydatetime()
                has_time = not (dt_utc.hour == 0 and dt_utc.minute == 0 and dt_utc.second == 0)
                return dt_utc, dt_utc.strftime("%Y-%m-%d"), has_time
        except Exception:
            pass

        return None, None, False

    @staticmethod
    def generate_news_id(
        ticker: str,
        published_at_iso: str,
        headline: str,
        source: Optional[str] = None,
        url: Optional[str] = None,
    ) -> str:
        """
        Generates deterministic SHA-256 hash ID.
        Includes optional source and url components to preserve source provenance
        and prevent distinct articles with identical tickers, headlines, and timestamps
        from different publishers/wires from being incorrectly merged.
        """
        clean_t = normalize_ticker(ticker)
        clean_h = headline.strip()
        parts = [clean_t, published_at_iso]
        if source and source.strip():
            parts.append(source.strip().lower())
        if url and url.strip():
            parts.append(url.strip())
        parts.append(clean_h)
        key = "|".join(parts)
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]

    def process_csv_chunk(
        self,
        chunk_df: pd.DataFrame,
        source_dataset: str = "fnspid_all_external",
        default_ticker: Optional[str] = None,
    ) -> pd.DataFrame:
        """Transforms a raw news DataFrame chunk into canonical normalized news records."""
        if chunk_df.empty:
            return pd.DataFrame()

        df = chunk_df.copy()
        col_map = {c.strip().lower(): c for c in df.columns}

        date_col = col_map.get("date")
        title_col = col_map.get("article_title", col_map.get("title", col_map.get("headline")))
        symbol_col = col_map.get("stock_symbol", col_map.get("symbol", col_map.get("ticker")))
        url_col = col_map.get("url")
        pub_col = col_map.get("publisher", col_map.get("source"))
        article_col = col_map.get("article", col_map.get("text", col_map.get("body")))

        now_utc = datetime.now(timezone.utc)
        records = []

        for _, row in df.iterrows():
            raw_date = row.get(date_col) if date_col else None
            raw_date_str = str(raw_date).strip() if pd.notna(raw_date) else ""
            utc_dt, iso_date, has_intraday = self.parse_datetime(raw_date)
            if utc_dt is None or iso_date is None:
                continue

            headline = str(row.get(title_col, "")).strip() if title_col and pd.notna(row.get(title_col)) else ""
            if not headline:
                continue

            if symbol_col and pd.notna(row.get(symbol_col)):
                raw_sym = str(row.get(symbol_col)).strip().upper()
            elif default_ticker:
                raw_sym = default_ticker.strip().upper()
            else:
                raw_sym = "UNKNOWN"

            url = str(row.get(url_col, "")).strip() if url_col and pd.notna(row.get(url_col)) else ""
            publisher = str(row.get(pub_col, "")).strip() if pub_col and pd.notna(row.get(pub_col)) else "Unknown"
            article = str(row.get(article_col, "")).strip() if article_col and pd.notna(row.get(article_col)) else ""
            has_body = bool(article and article.strip())

            clean_sym = normalize_ticker(raw_sym)
            company_id, mapping_status, mapping_provenance = self.resolve_company_mapping(clean_sym, iso_date)
            news_id = self.generate_news_id(clean_sym, utc_dt.isoformat(), headline, source=publisher, url=url)

            records.append({
                "news_id": news_id,
                "company_id": company_id if company_id else None,
                "ticker": clean_sym,
                "original_timestamp_raw": raw_date_str,
                "published_at": utc_dt,
                "published_date": iso_date,
                "ingestion_timestamp": now_utc,
                "mapping_status": mapping_status,
                "mapping_provenance": mapping_provenance,
                "has_intraday_time": has_intraday,
                "has_body_text": has_body,
                "headline": headline,
                "article_text": article,
                "source": publisher,
                "url": url,
                "source_dataset": source_dataset,
            })

        if not records:
            return pd.DataFrame()

        out_df = pd.DataFrame(records)
        return out_df

    def ingest_file(
        self,
        raw_csv_path: str,
        output_parquet_path: str,
        chunk_size: int = 10_000,
        source_dataset: str = "fnspid_all_external",
        default_ticker: Optional[str] = None,
        max_rows: Optional[int] = None,
    ) -> Dict[str, any]:
        """Streams raw news CSV in chunks and writes deduplicated Parquet output."""
        raw_path = Path(raw_csv_path)
        out_path = Path(output_parquet_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        writer: Optional[pq.ParquetWriter] = None
        seen_news_ids = set()
        total_records = 0
        duplicate_dropped = 0
        min_date = None
        max_date = None
        null_counts = {col: 0 for col in PROCESSED_NEWS_SCHEMA.names}
        rows_read = 0

        for chunk in pd.read_csv(raw_path, chunksize=chunk_size, low_memory=False):
            rows_read += len(chunk)
            processed_chunk = self.process_csv_chunk(
                chunk,
                source_dataset=source_dataset,
                default_ticker=default_ticker,
            )
            if processed_chunk.empty:
                continue

            # Deduplicate by news_id
            chunk_unique = processed_chunk[~processed_chunk["news_id"].isin(seen_news_ids)].copy()
            # Also deduplicate within the chunk itself
            chunk_unique = chunk_unique.drop_duplicates(subset=["news_id"])
            duplicate_dropped += len(processed_chunk) - len(chunk_unique)

            if chunk_unique.empty:
                continue

            for nid in chunk_unique["news_id"]:
                seen_news_ids.add(nid)

            total_records += len(chunk_unique)
            c_min = chunk_unique["published_date"].min()
            c_max = chunk_unique["published_date"].max()
            min_date = c_min if min_date is None or c_min < min_date else min_date
            max_date = c_max if max_date is None or c_max > max_date else max_date

            for col in null_counts:
                null_counts[col] += int(chunk_unique[col].isna().sum())

            table = pa.Table.from_pandas(chunk_unique, schema=PROCESSED_NEWS_SCHEMA)
            if writer is None:
                writer = pq.ParquetWriter(out_path, schema=PROCESSED_NEWS_SCHEMA, compression="snappy")
            writer.write_table(table)

            if max_rows and rows_read >= max_rows:
                logger.info(f"Reached max_rows limit ({max_rows:,}); stopping stream.")
                break

        if writer is not None:
            writer.close()

        stats = {
            "raw_file": str(raw_path),
            "output_file": str(out_path),
            "rows_read": rows_read,
            "record_count": total_records,
            "duplicates_dropped": duplicate_dropped,
            "min_date": min_date,
            "max_date": max_date,
            "null_counts": null_counts,
        }
        logger.info(
            f"Ingested news: {total_records:,} records ({duplicate_dropped:,} dupes dropped) -> {out_path}"
        )
        return stats

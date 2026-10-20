"""
Tiingo Market Data Ingestor.

Normalizes raw Tiingo JSON price responses into standardized PyArrow
Parquet files aligned with the Phase 1 canonical S&P 500 universe.
Preserves explicit separation between unadjusted and adjusted prices.
"""

import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.data.market.schema import PROCESSED_MARKET_SCHEMA
from src.data.market.base import BaseMarketIngestor

logger = logging.getLogger(__name__)

# Extended schema preserving explicit corporate actions from Tiingo
TIINGO_PROCESSED_MARKET_SCHEMA = pa.schema([
    ("company_id", pa.string()),          # Foreign key to sp500_universe (e.g. US_CIK_0000320193)
    ("ticker", pa.string()),              # Normalized uppercase ticker symbol
    ("timestamp", pa.timestamp("us", tz="UTC")), # Trading day timestamp at UTC midnight
    ("trading_date", pa.string()),        # ISO date YYYY-MM-DD
    ("open", pa.float64()),               # Unadjusted opening price
    ("high", pa.float64()),               # Unadjusted session high
    ("low", pa.float64()),                # Unadjusted session low
    ("close", pa.float64()),              # Unadjusted closing price
    ("adjusted_open", pa.float64()),      # Split & dividend adjusted open
    ("adjusted_high", pa.float64()),      # Split & dividend adjusted high
    ("adjusted_low", pa.float64()),       # Split & dividend adjusted low
    ("adjusted_close", pa.float64()),     # Split & dividend adjusted close
    ("volume", pa.int64()),               # Unadjusted share volume
    ("adjusted_volume", pa.int64()),      # Split adjusted share volume
    ("dividend_cash", pa.float64()),      # Cash dividend paid on date
    ("split_factor", pa.float64()),       # Split factor on date (1.0 = no split)
    ("source", pa.string()),              # Provenance tag: "tiingo_eod"
])


class TiingoIngestor(BaseMarketIngestor):
    """Ingests and normalizes Tiingo daily market prices."""

    def __init__(self, universe_df: Optional[pd.DataFrame] = None):
        self.universe_df = universe_df
        self._ticker_map: Dict[str, Dict[str, Any]] = {}
        if universe_df is not None:
            self._build_ticker_index(universe_df)

    def _build_ticker_index(self, universe_df: pd.DataFrame) -> None:
        """Indexes universe by ticker symbol."""
        for _, row in universe_df.iterrows():
            ticker_clean = str(row["ticker"]).upper().strip()
            if ticker_clean not in self._ticker_map:
                self._ticker_map[ticker_clean] = {
                    "company_id": row["company_id"],
                    "cik": row.get("cik"),
                    "company_name": row["company_name"],
                }
            if "." in ticker_clean:
                hyphen_variant = ticker_clean.replace(".", "-")
                if hyphen_variant not in self._ticker_map:
                    self._ticker_map[hyphen_variant] = self._ticker_map[ticker_clean]

    def normalize_prices(
        self,
        ticker: str,
        raw_records: List[Dict[str, Any]],
    ) -> pd.DataFrame:
        """Standard provider-independent normalization method conforming to BaseMarketIngestor."""
        return self.normalize_tiingo_prices(ticker, raw_records)

    def normalize_tiingo_prices(
        self,
        ticker: str,
        raw_prices: List[Dict[str, Any]],
    ) -> pd.DataFrame:
        """Normalizes raw Tiingo JSON price records into a structured DataFrame."""
        if not raw_prices:
            return pd.DataFrame(columns=[f.name for f in TIINGO_PROCESSED_MARKET_SCHEMA])

        ticker_clean = ticker.upper().strip()
        comp_info = self._ticker_map.get(ticker_clean, {
            "company_id": f"COMP_UNKNOWN_{ticker_clean}",
        })

        records = []
        for p in raw_prices:
            # Parse date string (e.g. "2023-10-16T00:00:00.000Z")
            raw_date = p.get("date", "")
            ts = pd.to_datetime(raw_date, utc=True)
            trading_date = ts.strftime("%Y-%m-%d")

            records.append({
                "company_id": comp_info["company_id"],
                "ticker": ticker_clean,
                "timestamp": ts,
                "trading_date": trading_date,
                "open": float(p.get("open", 0.0)),
                "high": float(p.get("high", 0.0)),
                "low": float(p.get("low", 0.0)),
                "close": float(p.get("close", 0.0)),
                "adjusted_open": float(p.get("adjOpen", 0.0)),
                "adjusted_high": float(p.get("adjHigh", 0.0)),
                "adjusted_low": float(p.get("adjLow", 0.0)),
                "adjusted_close": float(p.get("adjClose", 0.0)),
                "volume": int(p.get("volume", 0)),
                "adjusted_volume": int(p.get("adjVolume", 0)),
                "dividend_cash": float(p.get("divCash", 0.0)),
                "split_factor": float(p.get("splitFactor", 1.0)),
                "source": "tiingo_eod",
            })

        df = pd.DataFrame(records)
        df = df.drop_duplicates(subset=["ticker", "trading_date"])
        df = df.sort_values(by="trading_date")
        return df

    def save_processed_prices(self, df: pd.DataFrame, output_path: str) -> None:
        """Saves processed prices to Parquet using TIINGO_PROCESSED_MARKET_SCHEMA."""
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        table = pa.Table.from_pandas(df, schema=TIINGO_PROCESSED_MARKET_SCHEMA, preserve_index=False)
        pq.write_table(table, str(out), compression="snappy")
        logger.info(f"Saved {len(df)} processed Tiingo market records to {out}")

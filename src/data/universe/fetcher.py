"""
Fetcher module for S&P 500 universe raw datasets.

Handles downloading and caching raw data from Wikipedia, GitHub historical archives,
and SEC EDGAR mapping resources.
"""

from __future__ import annotations

import io
import json
import logging
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import pandas as pd

logger = logging.getLogger(__name__)

# Default source endpoints
SOURCES = {
    "wikipedia_current": {
        "url": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        "description": "Wikipedia current S&P 500 constituents list with sectors and CIKs",
        "filename_json": "wikipedia_current_constituents.json",
        "filename_csv": "wikipedia_current_constituents.csv",
    },
    "wikipedia_historical_changes": {
        "url": "https://en.wikipedia.org/wiki/Historical_components_of_the_S%26P_500",
        "description": "Wikipedia historical S&P 500 additions, removals, and corporate change events",
        "filename_json": "wikipedia_historical_changes.json",
        "filename_csv": "wikipedia_historical_changes.csv",
    },
    "historical_intervals": {
        "url": "https://raw.githubusercontent.com/fja05680/sp500/master/sp500_ticker_start_end.csv",
        "description": "Historical S&P 500 membership intervals (start_date, end_date) 1996-2024",
        "filename_csv": "sp500_ticker_start_end_raw.csv",
    },
    "hanshof_constituents": {
        "url": "https://raw.githubusercontent.com/hanshof/sp500_constituents/master/sp500_constituents.csv",
        "description": "Historical constituents metadata with CIKs, founding dates, and GICS sectors",
        "filename_csv": "hanshof_sp500_constituents_raw.csv",
    },
    "hanshof_daily_components": {
        "url": "https://raw.githubusercontent.com/hanshof/sp500_constituents/master/sp_500_historical_components.csv",
        "description": "Historical daily index constituent snapshot matrix 1996-present",
        "filename_csv": "hanshof_daily_components_raw.csv",
    },
    "sec_company_tickers": {
        "url": "https://raw.githubusercontent.com/team-headstart/Financial-Analysis-and-Automation-with-LLMs/main/company_tickers.json",
        "description": "SEC EDGAR active and historical company ticker to CIK mapping registry",
        "filename_json": "sec_company_tickers_raw.json",
    },
}

USER_AGENT = "FinancialIntelligenceAgent/1.0 (academic.research@finintelligence.org)"


def _download_content(url: str, timeout: int = 15) -> bytes:
    """Download content from a given URL using a standardized User-Agent."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/json,text/csv,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


class RawDataFetcher:
    """Orchestrates downloading and storing pristine raw datasets."""

    def __init__(self, raw_dir: str | Path = "data/raw/universe"):
        self.raw_dir = Path(raw_dir)
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    def fetch_all(self, force: bool = False) -> Dict[str, Any]:
        """Fetch all raw sources and write metadata manifest."""
        manifest: Dict[str, Any] = {
            "retrieval_timestamp": datetime.now(timezone.utc).isoformat(),
            "sources": {},
        }

        # 1. Fetch current constituents from Wikipedia
        current_csv = self.raw_dir / SOURCES["wikipedia_current"]["filename_csv"]
        current_json = self.raw_dir / SOURCES["wikipedia_current"]["filename_json"]
        if force or not current_csv.exists():
            logger.info("Fetching Wikipedia current constituents...")
            html = _download_content(SOURCES["wikipedia_current"]["url"]).decode("utf-8")
            tables = pd.read_html(io.StringIO(html))
            df_current = tables[0]
            # Standardize column names
            df_current.to_csv(current_csv, index=False)
            df_current.to_json(current_json, orient="records", indent=2)
            manifest["sources"]["wikipedia_current"] = {
                "records": len(df_current),
                "url": SOURCES["wikipedia_current"]["url"],
                "saved_files": [str(current_csv), str(current_json)],
            }
        else:
            logger.info("Wikipedia current constituents already present. Skipping.")

        # 2. Fetch historical changes from Wikipedia
        changes_csv = self.raw_dir / SOURCES["wikipedia_historical_changes"]["filename_csv"]
        changes_json = self.raw_dir / SOURCES["wikipedia_historical_changes"]["filename_json"]
        if force or not changes_csv.exists():
            logger.info("Fetching Wikipedia historical changes...")
            html_changes = _download_content(SOURCES["wikipedia_historical_changes"]["url"]).decode("utf-8")
            tables_changes = pd.read_html(io.StringIO(html_changes))
            df_changes = tables_changes[0]
            # Flatten MultiIndex columns if present
            if isinstance(df_changes.columns, pd.MultiIndex):
                flat_cols = []
                for col in df_changes.columns:
                    top, sub = col[0], col[1]
                    if top == sub or not sub or "Unnamed" in sub:
                        flat_cols.append(top.strip())
                    else:
                        flat_cols.append(f"{top.strip()}_{sub.strip()}")
                df_changes.columns = flat_cols

            df_changes.to_csv(changes_csv, index=False)
            df_changes.to_json(changes_json, orient="records", indent=2)
            manifest["sources"]["wikipedia_historical_changes"] = {
                "records": len(df_changes),
                "url": SOURCES["wikipedia_historical_changes"]["url"],
                "saved_files": [str(changes_csv), str(changes_json)],
            }
        else:
            logger.info("Wikipedia historical changes already present. Skipping.")

        # 3. Fetch historical membership intervals (fja05680)
        intervals_file = self.raw_dir / SOURCES["historical_intervals"]["filename_csv"]
        if force or not intervals_file.exists():
            logger.info("Fetching historical membership intervals...")
            raw_bytes = _download_content(SOURCES["historical_intervals"]["url"])
            df_int = pd.read_csv(io.BytesIO(raw_bytes))
            df_int.to_csv(intervals_file, index=False)
            manifest["sources"]["historical_intervals"] = {
                "records": len(df_int),
                "url": SOURCES["historical_intervals"]["url"],
                "saved_file": str(intervals_file),
            }
        else:
            logger.info("Historical intervals already present. Skipping.")

        # 4. Fetch Hanshof constituents metadata
        hanshof_const_file = self.raw_dir / SOURCES["hanshof_constituents"]["filename_csv"]
        if force or not hanshof_const_file.exists():
            logger.info("Fetching Hanshof constituents metadata...")
            raw_bytes = _download_content(SOURCES["hanshof_constituents"]["url"])
            df_hc = pd.read_csv(io.BytesIO(raw_bytes))
            df_hc.to_csv(hanshof_const_file, index=False)
            manifest["sources"]["hanshof_constituents"] = {
                "records": len(df_hc),
                "url": SOURCES["hanshof_constituents"]["url"],
                "saved_file": str(hanshof_const_file),
            }
        else:
            logger.info("Hanshof constituents already present. Skipping.")

        # 5. Fetch Hanshof daily components snapshot
        hanshof_comp_file = self.raw_dir / SOURCES["hanshof_daily_components"]["filename_csv"]
        if force or not hanshof_comp_file.exists():
            logger.info("Fetching Hanshof daily components snapshot matrix...")
            raw_bytes = _download_content(SOURCES["hanshof_daily_components"]["url"])
            df_comp = pd.read_csv(io.BytesIO(raw_bytes))
            df_comp.to_csv(hanshof_comp_file, index=False)
            manifest["sources"]["hanshof_daily_components"] = {
                "records": len(df_comp),
                "url": SOURCES["hanshof_daily_components"]["url"],
                "saved_file": str(hanshof_comp_file),
            }
        else:
            logger.info("Hanshof daily components already present. Skipping.")

        # 6. Fetch SEC company tickers mapping
        sec_file = self.raw_dir / SOURCES["sec_company_tickers"]["filename_json"]
        if force or not sec_file.exists():
            logger.info("Fetching SEC company tickers JSON...")
            raw_bytes = _download_content(SOURCES["sec_company_tickers"]["url"])
            sec_dict = json.loads(raw_bytes.decode("utf-8"))
            with open(sec_file, "w", encoding="utf-8") as f:
                json.dump(sec_dict, f, indent=2)
            manifest["sources"]["sec_company_tickers"] = {
                "records": len(sec_dict),
                "url": SOURCES["sec_company_tickers"]["url"],
                "saved_file": str(sec_file),
            }
        else:
            logger.info("SEC company tickers already present. Skipping.")

        # Save metadata manifest
        manifest_path = self.raw_dir / "retrieval_metadata.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        logger.info(f"Raw data download complete. Manifest saved to {manifest_path}")
        return manifest

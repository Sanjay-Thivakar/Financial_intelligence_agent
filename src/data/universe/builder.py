"""
UniverseBuilder module.

Fuses raw S&P 500 constituents, historical additions/removals, membership intervals,
and SEC EDGAR registries into a canonical company-identity universe layer.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from src.data.universe.ticker_mapping import (
    HISTORICAL_CIK_LOOKUP,
    TICKER_SUCCESSIONS,
    format_cik,
    generate_company_id,
    normalize_ticker,
)

logger = logging.getLogger(__name__)


class UniverseBuilder:
    """Builds canonical point-in-time S&P 500 company universe."""

    def __init__(self, raw_dir: str | Path = "data/raw/universe"):
        self.raw_dir = Path(raw_dir)

    def _load_raw_data(self) -> Dict[str, Any]:
        """Load all raw inputs from the raw data directory."""
        # 1. Historical intervals
        intervals_csv = self.raw_dir / "sp500_ticker_start_end_raw.csv"
        df_intervals = pd.read_csv(intervals_csv)

        # 2. Wikipedia current constituents
        current_csv = self.raw_dir / "wikipedia_current_constituents.csv"
        df_current = pd.read_csv(current_csv)

        # 3. Wikipedia historical changes
        changes_csv = self.raw_dir / "wikipedia_historical_changes.csv"
        df_changes = pd.read_csv(changes_csv)

        # 4. SEC company tickers JSON
        sec_json = self.raw_dir / "sec_company_tickers_raw.json"
        with open(sec_json, "r", encoding="utf-8") as f:
            sec_dict = json.load(f)

        # 5. Hanshof metadata
        hanshof_csv = self.raw_dir / "hanshof_sp500_constituents_raw.csv"
        df_hanshof = pd.read_csv(hanshof_csv) if hanshof_csv.exists() else pd.DataFrame()

        return {
            "intervals": df_intervals,
            "current": df_current,
            "changes": df_changes,
            "sec": sec_dict,
            "hanshof": df_hanshof,
        }

    def build_canonical_universe(self) -> pd.DataFrame:
        """Construct the canonical S&P 500 company universe dataset.

        Returns DataFrame with columns:
        - company_id: Canonical company identifier (US_CIK_<cik> or COMP_NO_CIK_<ticker>)
        - ticker: Point-in-time trading ticker symbol (e.g. FB, META, BRK.B)
        - cik: 10-digit zero-padded SEC Central Index Key (or None)
        - company_name: Legal/operating company name
        - sector: GICS Sector (or None if unavailable)
        - effective_from: Membership interval start date (YYYY-MM-DD)
        - effective_to: Membership interval end date (YYYY-MM-DD or None if currently active)
        """
        raw = self._load_raw_data()
        df_intervals = raw["intervals"].copy()
        df_current = raw["current"]
        df_changes = raw["changes"]
        sec_dict = raw["sec"]
        df_hanshof = raw["hanshof"]

        # Step 1: Build SEC Lookup Maps
        sec_ticker_to_cik: Dict[str, str] = {}
        sec_ticker_to_title: Dict[str, str] = {}
        for item in sec_dict.values():
            tick = normalize_ticker(item.get("ticker", ""))
            cik_fmt = format_cik(item.get("cik_str"))
            title = item.get("title", "").strip()
            if tick and cik_fmt:
                sec_ticker_to_cik[tick] = cik_fmt
                if title:
                    sec_ticker_to_title[tick] = title

        # Step 2: Build Wikipedia Current Maps
        wiki_ticker_to_cik: Dict[str, str] = {}
        wiki_ticker_to_name: Dict[str, str] = {}
        wiki_ticker_to_sector: Dict[str, str] = {}
        for _, row in df_current.iterrows():
            sym = normalize_ticker(str(row.get("Symbol", "")))
            cik_fmt = format_cik(row.get("CIK"))
            sec_name = str(row.get("Security", "")).strip()
            sector = str(row.get("GICS Sector", "")).strip()
            if sym:
                if cik_fmt:
                    wiki_ticker_to_cik[sym] = cik_fmt
                if sec_name:
                    wiki_ticker_to_name[sym] = sec_name
                if sector:
                    wiki_ticker_to_sector[sym] = sector

        # Step 3: Build Hanshof Metadata Maps
        hanshof_ticker_to_sector: Dict[str, str] = {}
        hanshof_ticker_to_name: Dict[str, str] = {}
        hanshof_ticker_to_cik: Dict[str, str] = {}
        if not df_hanshof.empty:
            for _, row in df_hanshof.iterrows():
                sym = normalize_ticker(str(row.get("symbol", "")))
                sec_name = str(row.get("security", "")).strip()
                sector = str(row.get("gics sector", "")).strip()
                cik_fmt = format_cik(row.get("cik"))
                if sym:
                    if sector:
                        hanshof_ticker_to_sector[sym] = sector
                    if sec_name:
                        hanshof_ticker_to_name[sym] = sec_name
                    if cik_fmt:
                        hanshof_ticker_to_cik[sym] = cik_fmt

        # Step 4: Build Historical Changes Name Map
        changes_name_map: Dict[str, str] = {}
        for _, row in df_changes.iterrows():
            add_t = normalize_ticker(str(row.get("Added_Ticker", "")))
            add_s = str(row.get("Added_Security", "")).strip()
            rem_t = normalize_ticker(str(row.get("Removed_Ticker", "")))
            rem_s = str(row.get("Removed_Security", "")).strip()
            if add_t and add_s and add_s != "nan":
                changes_name_map[add_t] = add_s
            if rem_t and rem_s and rem_s != "nan":
                changes_name_map[rem_t] = rem_s

        # Step 5: Normalize and reconcile intervals
        # Ensure ticker is normalized
        df_intervals["ticker"] = df_intervals["ticker"].apply(normalize_ticker)
        df_intervals["start_date"] = pd.to_datetime(df_intervals["start_date"]).dt.strftime("%Y-%m-%d")
        df_intervals["end_date"] = pd.to_datetime(df_intervals["end_date"]).dt.strftime("%Y-%m-%d")

        # Reconcile recent additions & removals (e.g. September 21, 2026 changes)
        # Verify which tickers are listed as current in Wikipedia vs intervals
        current_symbols = set(wiki_ticker_to_name.keys())
        active_in_intervals = set(df_intervals[df_intervals["end_date"].isna()]["ticker"].unique())

        # Removals that occurred post-intervals-cut (still marked active in intervals but removed in Wikipedia changes)
        # From Wikipedia changes: TAP, TTD, BLDR removed on 2026-09-21
        removals_to_apply = {
            "TAP": "2026-09-21",
            "TTD": "2026-09-21",
            "BLDR": "2026-09-21",
        }
        for t, end_d in removals_to_apply.items():
            mask = (df_intervals["ticker"] == t) & (df_intervals["end_date"].isna())
            if mask.any():
                df_intervals.loc[mask, "end_date"] = end_d
                logger.info(f"Reconciled removal for {t}: set end_date = {end_d}")

        # Additions that occurred post-intervals-cut: BE, P, ILMN added on 2026-09-21
        additions_to_apply = [
            {"ticker": "BE", "start_date": "2026-09-21", "end_date": None},
            {"ticker": "P", "start_date": "2026-09-21", "end_date": None},
            {"ticker": "ILMN", "start_date": "2026-09-21", "end_date": None},
        ]
        for item in additions_to_apply:
            t = item["ticker"]
            s_d = item["start_date"]
            # Check if this active interval already exists
            mask = (df_intervals["ticker"] == t) & (df_intervals["start_date"] == s_d)
            if not mask.any():
                df_intervals = pd.concat([df_intervals, pd.DataFrame([item])], ignore_index=True)
                logger.info(f"Reconciled addition for {t}: added interval starting {s_d}")

        # Step 6: Resolve CIK, Name, Sector, and Company ID for every interval
        records: List[Dict[str, Any]] = []

        for _, row in df_intervals.iterrows():
            ticker = row["ticker"]
            start_date = row["start_date"]
            end_date = None if pd.isna(row["end_date"]) else row["end_date"]

            # CIK Resolution cascade:
            # 1. Curated historical lookup (authoritative for delisted/acquired historical tickers)
            # 2. Wikipedia current constituent map
            # 3. SEC company tickers JSON map
            # 4. Successor ticker lookup (via TICKER_SUCCESSIONS)
            # 5. Hanshof metadata map
            cik: Optional[str] = None
            company_name: Optional[str] = None
            sector: Optional[str] = None

            # Special case for reused ticker 'Q' (Qwest in 2000-2011 vs Qnity Electronics in 2025+)
            if ticker == "Q":
                if start_date >= "2025-01-01":
                    company_name = "Qnity Electronics"
                    sector = "Information Technology"
                    cik = wiki_ticker_to_cik.get("Q") or "0002058873"
                else:
                    company_name = "Qwest Communications International Inc."
                    sector = "Communication Services"
                    cik = "0001037949"

            if not cik and ticker in HISTORICAL_CIK_LOOKUP:
                h_cik, h_name, h_sector = HISTORICAL_CIK_LOOKUP[ticker]
                cik = format_cik(h_cik)
                company_name = h_name
                sector = h_sector

            if not cik and ticker in wiki_ticker_to_cik:
                cik = wiki_ticker_to_cik[ticker]
            if not cik and ticker in sec_ticker_to_cik:
                cik = sec_ticker_to_cik[ticker]

            # Check successor if CIK still not resolved (exclude Qnity Electronics which reused Q in 2025)
            if not cik and ticker in TICKER_SUCCESSIONS and not (ticker == "Q" and start_date >= "2025-01-01"):
                succ = TICKER_SUCCESSIONS[ticker]
                if succ in wiki_ticker_to_cik:
                    cik = wiki_ticker_to_cik[succ]
                elif succ in sec_ticker_to_cik:
                    cik = sec_ticker_to_cik[succ]
                elif succ in HISTORICAL_CIK_LOOKUP:
                    cik = format_cik(HISTORICAL_CIK_LOOKUP[succ][0])

            if not cik and ticker in hanshof_ticker_to_cik:
                cik = hanshof_ticker_to_cik[ticker]

            # Company Name resolution cascade:
            if not company_name:
                if ticker in wiki_ticker_to_name:
                    company_name = wiki_ticker_to_name[ticker]
                elif ticker in sec_ticker_to_title:
                    company_name = sec_ticker_to_title[ticker]
                elif ticker in changes_name_map:
                    company_name = changes_name_map[ticker]
                elif ticker in hanshof_ticker_to_name:
                    company_name = hanshof_ticker_to_name[ticker]
                elif ticker in TICKER_SUCCESSIONS:
                    succ = TICKER_SUCCESSIONS[ticker]
                    company_name = (
                        wiki_ticker_to_name.get(succ)
                        or sec_ticker_to_title.get(succ)
                        or changes_name_map.get(succ)
                    )

            if not company_name:
                company_name = ticker  # Fallback to symbol if entirely unrecorded

            # Sector resolution cascade:
            if not sector:
                if ticker in wiki_ticker_to_sector:
                    sector = wiki_ticker_to_sector[ticker]
                elif ticker in hanshof_ticker_to_sector:
                    sector = hanshof_ticker_to_sector[ticker]
                elif ticker in TICKER_SUCCESSIONS:
                    succ = TICKER_SUCCESSIONS[ticker]
                    sector = wiki_ticker_to_sector.get(succ) or hanshof_ticker_to_sector.get(succ)

            # Generate canonical Company ID
            company_id = generate_company_id(cik, company_name, ticker)

            records.append({
                "company_id": company_id,
                "ticker": ticker,
                "cik": cik,
                "company_name": company_name,
                "sector": sector if sector and sector.lower() != "nan" else None,
                "effective_from": start_date,
                "effective_to": end_date,
            })

        df_universe = pd.DataFrame(records)

        # Sort canonically by company_id, effective_from, ticker
        df_universe = df_universe.sort_values(
            by=["company_id", "effective_from", "ticker"],
            ascending=[True, True, True],
        ).reset_index(drop=True)

        return df_universe

    @staticmethod
    def get_constituents_at_date(universe_df: pd.DataFrame, as_of_date: str) -> pd.DataFrame:
        """Point-in-time constituent lookup for avoiding survivorship bias.

        Uses standard half-open interval [effective_from, effective_to).
        A company is a constituent on as_of_date if:
            effective_from <= as_of_date < effective_to (or effective_to is None)
        """
        target = pd.to_datetime(as_of_date).strftime("%Y-%m-%d")
        mask = (universe_df["effective_from"] <= target) & (
            universe_df["effective_to"].isna() | (universe_df["effective_to"] > target)
        )
        return universe_df[mask].copy().reset_index(drop=True)

"""
SEC EDGAR Data Ingestor.

Processes raw SEC submissions and XBRL company facts into normalized,
point-in-time aligned DataFrames joined against the Phase 1 canonical universe.
"""

import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.data.sec.schema import PROCESSED_SEC_FACT_SCHEMA, PROCESSED_SEC_8K_SCHEMA

logger = logging.getLogger(__name__)

# Core GAAP concepts essential for fundamental equity valuation
CORE_GAAP_CONCEPTS = {
    # Revenue
    "RevenueFromContractWithCustomerExcludingAssessedTax": "Revenues",
    "Revenues": "Revenues",
    "SalesRevenueNet": "Revenues",
    # Net Income
    "NetIncomeLoss": "Net Income",
    "ProfitLoss": "Net Income",
    # Operating Income
    "OperatingIncomeLoss": "Operating Income",
    # Balance Sheet Assets
    "Assets": "Total Assets",
    "AssetsCurrent": "Current Assets",
    "CashAndCashEquivalentsAtCarryingValue": "Cash and Cash Equivalents",
    # Balance Sheet Liabilities & Equity
    "Liabilities": "Total Liabilities",
    "LiabilitiesCurrent": "Current Liabilities",
    "StockholdersEquity": "Stockholders' Equity",
    # Cash Flows
    "NetCashProvidedByUsedInOperatingActivities": "Operating Cash Flow",
    "PaymentsToAcquirePropertyPlantAndEquipment": "Capital Expenditures",
    "PaymentsToAcquireProductiveAssets": "Capital Expenditures",
    # Per Share
    "EarningsPerShareDiluted": "Diluted EPS",
    "EarningsPerShareBasic": "Basic EPS",
}


class SECIngestor:
    """Ingests and normalizes SEC EDGAR submissions and XBRL financial facts."""

    def __init__(self, universe_df: Optional[pd.DataFrame] = None):
        self.universe_df = universe_df
        self._cik_to_company: Dict[str, Dict[str, Any]] = {}
        if universe_df is not None:
            self._build_universe_cache(universe_df)

    def _build_universe_cache(self, universe_df: pd.DataFrame) -> None:
        """Indexes universe by 10-digit CIK for canonical company lookup."""
        for _, row in universe_df.iterrows():
            cik_val = row.get("cik")
            if pd.notna(cik_val) and cik_val:
                cik_clean = str(cik_val).strip().zfill(10)
                if cik_clean not in self._cik_to_company:
                    self._cik_to_company[cik_clean] = {
                        "company_id": row["company_id"],
                        "ticker": row["ticker"],
                        "company_name": row["company_name"],
                    }

    def parse_submissions_accession_map(self, submissions_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """
        Builds a lookup map from accession number to filing metadata,
        specifically isolating the exact acceptanceDateTime.
        """
        recent = submissions_data.get("filings", {}).get("recent", {})
        accns = recent.get("accessionNumber", [])
        forms = recent.get("form", [])
        filed_dates = recent.get("filingDate", [])
        report_dates = recent.get("reportDate", [])
        acceptance_dts = recent.get("acceptanceDateTime", [])
        primary_docs = recent.get("primaryDocument", [])
        items = recent.get("items", [])

        accession_map = {}
        for i, accn in enumerate(accns):
            accession_map[accn] = {
                "form": forms[i] if i < len(forms) else "",
                "filed_date": filed_dates[i] if i < len(filed_dates) else "",
                "report_date": report_dates[i] if i < len(report_dates) else "",
                "acceptance_datetime": acceptance_dts[i] if i < len(acceptance_dts) else None,
                "primary_document": primary_docs[i] if i < len(primary_docs) else "",
                "items": items[i] if i < len(items) else "",
            }
        return accession_map

    def extract_8k_filings(
        self,
        cik: str,
        submissions_data: Dict[str, Any],
        max_filings: int = 50,
    ) -> pd.DataFrame:
        """Extracts recent Form 8-K material event filings."""
        cik_clean = str(cik).strip().zfill(10)
        company_info = self._cik_to_company.get(cik_clean, {
            "company_id": f"US_CIK_{cik_clean}",
            "ticker": submissions_data.get("tickers", [cik_clean])[0] if submissions_data.get("tickers") else cik_clean,
        })

        recent = submissions_data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accns = recent.get("accessionNumber", [])
        filed_dates = recent.get("filingDate", [])
        acceptance_dts = recent.get("acceptanceDateTime", [])
        primary_docs = recent.get("primaryDocument", [])
        items = recent.get("items", [])

        rows = []
        for i, form in enumerate(forms):
            if form in ("8-K", "8-K/A"):
                accn = accns[i] if i < len(accns) else ""
                accn_no_hyphen = accn.replace("-", "")
                primary_doc = primary_docs[i] if i < len(primary_docs) else ""
                filing_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik_clean)}/{accn_no_hyphen}/{primary_doc}"

                accept_dt = acceptance_dts[i] if i < len(acceptance_dts) else None
                if accept_dt:
                    ts = pd.to_datetime(accept_dt, utc=True)
                else:
                    ts = pd.to_datetime(filed_dates[i] if i < len(filed_dates) else "2000-01-01", utc=True)

                rows.append({
                    "company_id": company_info["company_id"],
                    "cik": cik_clean,
                    "ticker": company_info["ticker"],
                    "form": form,
                    "filing_date": filed_dates[i] if i < len(filed_dates) else "",
                    "acceptance_timestamp": ts,
                    "accession_number": accn,
                    "items": str(items[i]) if i < len(items) and items[i] else "",
                    "primary_document": primary_doc,
                    "filing_url": filing_url,
                    "source": "sec_edgar_submissions",
                })
                if len(rows) >= max_filings:
                    break

        if not rows:
            return pd.DataFrame(columns=[f.name for f in PROCESSED_SEC_8K_SCHEMA])
        df = pd.DataFrame(rows)
        return df

    def extract_8k_events(
        self,
        cik: str,
        submissions_input: Any,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """Extracts Form 8-K material events using SECEventExtractor."""
        extractor = SECEventExtractor(universe_df=self.universe_df)
        return extractor.extract_events(
            submissions_input=submissions_input,
            cik=cik,
            start_date=start_date,
            end_date=end_date,
        )

    def extract_financial_facts(
        self,
        cik: str,
        facts_data: Dict[str, Any],
        accession_map: Dict[str, Dict[str, Any]],
        concepts_to_extract: Optional[Dict[str, str]] = None,
    ) -> pd.DataFrame:
        """
        Extracts standardized XBRL financial facts and joins each fact
        against accession_map to record the exact point-in-time acceptanceDateTime.
        """
        cik_clean = str(cik).strip().zfill(10)
        company_info = self._cik_to_company.get(cik_clean, {
            "company_id": f"US_CIK_{cik_clean}",
            "ticker": facts_data.get("entityName", cik_clean),
        })

        target_concepts = concepts_to_extract or CORE_GAAP_CONCEPTS
        gaap_facts = facts_data.get("facts", {}).get("us-gaap", {})

        records = []
        for tag, normalized_label in target_concepts.items():
            if tag not in gaap_facts:
                continue
            fact_obj = gaap_facts[tag]
            units_dict = fact_obj.get("units", {})

            for unit_key, observations in units_dict.items():
                for obs in observations:
                    # Filter to core periodic forms: 10-K and 10-Q
                    form = obs.get("form", "")
                    if form not in ("10-K", "10-Q", "10-K/A", "10-Q/A"):
                        continue

                    val = obs.get("val")
                    if val is None:
                        continue

                    accn = obs.get("accn", "")
                    filed_date = obs.get("filed", "")
                    period_end = obs.get("end", "")
                    period_start = obs.get("start")
                    fy = obs.get("fy", 0)
                    fp = obs.get("fp", "")

                    # Point-in-time acceptance timestamp resolution
                    accn_meta = accession_map.get(accn, {})
                    accept_dt = accn_meta.get("acceptance_datetime")

                    if accept_dt:
                        ts = pd.to_datetime(accept_dt, utc=True)
                    elif filed_date:
                        # Conservative fallback if accn not in recent filings array:
                        # End-of-day UTC on filing date prevents look-ahead
                        ts = pd.to_datetime(f"{filed_date} 23:59:59", utc=True)
                    else:
                        ts = pd.to_datetime("2000-01-01 00:00:00", utc=True)

                    records.append({
                        "company_id": company_info["company_id"],
                        "cik": cik_clean,
                        "ticker": company_info["ticker"],
                        "taxonomy": "us-gaap",
                        "concept": tag,
                        "label": normalized_label,
                        "period_start": period_start,
                        "period_end": period_end,
                        "fiscal_year": int(fy) if fy else 0,
                        "fiscal_period": fp,
                        "form": form,
                        "filed_date": filed_date,
                        "acceptance_timestamp": ts,
                        "accession_number": accn,
                        "value": float(val),
                        "unit": unit_key,
                        "source": "sec_edgar_companyfacts",
                    })

        if not records:
            return pd.DataFrame(columns=[f.name for f in PROCESSED_SEC_FACT_SCHEMA])

        df = pd.DataFrame(records)
        # Deduplicate identical (concept, period_end, form, filed_date, value)
        df = df.drop_duplicates(subset=["cik", "concept", "period_end", "form", "filed_date", "accession_number"])
        df = df.sort_values(by=["concept", "period_end", "acceptance_timestamp"])
        return df

    def save_processed_facts(self, df: pd.DataFrame, output_path: str) -> None:
        """Saves processed facts DataFrame as Parquet with strict PyArrow schema."""
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        table = pa.Table.from_pandas(df, schema=PROCESSED_SEC_FACT_SCHEMA, preserve_index=False)
        pq.write_table(table, str(out), compression="snappy")
        logger.info(f"Saved {len(df)} processed SEC facts to {out}")

    def save_processed_8k(self, df: pd.DataFrame, output_path: str) -> None:
        """Saves processed 8-K DataFrame as Parquet with strict PyArrow schema."""
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        table = pa.Table.from_pandas(df, schema=PROCESSED_SEC_8K_SCHEMA, preserve_index=False)
        pq.write_table(table, str(out), compression="snappy")
        logger.info(f"Saved {len(df)} processed SEC 8-K records to {out}")

    @staticmethod
    def query_fact_as_of(
        df: pd.DataFrame,
        concept: str,
        period_end: str,
        as_of_timestamp: pd.Timestamp,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves the authoritative fact value as of a specific decision/prediction timestamp.
        Guarantees zero look-ahead bias and restatement-safe retrieval:
        1. Filters only observations where acceptance_timestamp <= as_of_timestamp.
        2. If multiple filings exist (e.g. original 10-K and later 10-K/A amendment),
           selects the latest filing publicly available as of the decision cutoff.
        """
        if df.empty:
            return None

        mask = (df["concept"] == concept) & (df["period_end"] == period_end)
        matches = df[mask]
        if matches.empty:
            return None

        if as_of_timestamp.tzinfo is None:
            as_of_utc = as_of_timestamp.tz_localize("UTC")
        else:
            as_of_utc = as_of_timestamp.tz_convert("UTC")

        available = matches[matches["acceptance_timestamp"] <= as_of_utc]
        if available.empty:
            return None

        latest_fact = available.sort_values(by="acceptance_timestamp").iloc[-1]
        return latest_fact.to_dict()


class SECEventExtractor:
    """
    Structured SEC Form 8-K Corporate Event Extractor.
    Extracts point-in-time event metadata from official SEC EDGAR submissions.
    Enforces CIK-based company identity, deduplication by accession number,
    point-in-time acceptance timestamp validation, and verified Item classification.
    """

    PRIORITY_ITEMS = ("1.01", "2.02", "5.02", "7.01", "8.01")

    def __init__(self, universe_df: Optional[pd.DataFrame] = None):
        self.universe_df = universe_df
        self._cik_to_company: Dict[str, Dict[str, Any]] = {}
        if universe_df is not None:
            self._build_universe_cache(universe_df)

    def _build_universe_cache(self, universe_df: pd.DataFrame) -> None:
        """Indexes universe by 10-digit CIK for canonical company lookup."""
        for _, row in universe_df.iterrows():
            cik_val = row.get("cik")
            if pd.notna(cik_val) and cik_val:
                cik_clean = str(cik_val).strip().zfill(10)
                if cik_clean not in self._cik_to_company:
                    self._cik_to_company[cik_clean] = {
                        "company_id": row["company_id"],
                        "ticker": row["ticker"],
                        "company_name": row.get("company_name", ""),
                    }

    @staticmethod
    def parse_items(raw_items: Any) -> List[str]:
        """
        Parses raw Form 8-K items from SEC submissions metadata into a standardized list of item codes.
        Handles comma-separated strings (e.g. '2.02,9.01'), lists, and stringified lists.
        Strips whitespace and preserves canonical item numbers (e.g. '1.01', '2.02').
        """
        if raw_items is None or pd.isna(raw_items):
            return []
        if isinstance(raw_items, (list, tuple)):
            items_list = [str(x).strip() for x in raw_items if str(x).strip()]
        else:
            s = str(raw_items).strip()
            if s.startswith("[") and s.endswith("]"):
                s = s[1:-1].replace("'", "").replace('"', "")
            items_list = [x.strip() for x in s.split(",") if x.strip()]

        cleaned = []
        for itm in items_list:
            clean_itm = itm.strip()
            if clean_itm and clean_itm not in cleaned:
                cleaned.append(clean_itm)
        return cleaned

    def extract_events(
        self,
        submissions_input: Any,
        cik: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Extracts structured Form 8-K and 8-K/A corporate-event records.
        :param submissions_input: Either a single submissions dict, a list of submissions dicts,
                                  or a list of file paths.
        :param cik: 10-digit SEC CIK string.
        :param start_date: Optional inclusive start date (YYYY-MM-DD).
        :param end_date: Optional inclusive end date (YYYY-MM-DD).
        :return: DataFrame of extracted 8-K events with full provenance and status flags.
        """
        # Normalize input to list of dicts
        sub_dicts: List[Dict[str, Any]] = []
        if isinstance(submissions_input, list):
            for item in submissions_input:
                if isinstance(item, dict):
                    sub_dicts.append(item)
                elif isinstance(item, (str, Path)) and Path(item).exists():
                    import json
                    with open(item, "r", encoding="utf-8") as f:
                        sub_dicts.append(json.load(f))
        elif isinstance(submissions_input, dict):
            sub_dicts.append(submissions_input)
        elif isinstance(submissions_input, (str, Path)) and Path(submissions_input).exists():
            import json
            with open(submissions_input, "r", encoding="utf-8") as f:
                sub_dicts.append(json.load(f))

        # Determine CIK
        cik_clean = ""
        if cik:
            cik_clean = str(cik).strip().zfill(10)
        elif sub_dicts and "cik" in sub_dicts[0]:
            cik_clean = str(sub_dicts[0]["cik"]).strip().zfill(10)

        company_info = self._cik_to_company.get(cik_clean, {
            "company_id": f"US_CIK_{cik_clean}" if cik_clean else "UNKNOWN",
            "ticker": sub_dicts[0].get("tickers", [cik_clean])[0] if sub_dicts and sub_dicts[0].get("tickers") else (cik_clean or "UNKNOWN"),
        })

        seen_accessions = set()
        rows = []

        for sub_data in sub_dicts:
            # Check if this dict has filings.recent or is top-level (paginated)
            if "filings" in sub_data and "recent" in sub_data["filings"]:
                block = sub_data["filings"]["recent"]
            else:
                block = sub_data

            forms = block.get("form", [])
            accns = block.get("accessionNumber", [])
            filed_dates = block.get("filingDate", [])
            acceptance_dts = block.get("acceptanceDateTime", [])
            primary_docs = block.get("primaryDocument", [])
            items_raw = block.get("items", [])

            n_filings = len(forms)
            for i in range(n_filings):
                form = forms[i] if i < len(forms) else ""
                if form not in ("8-K", "8-K/A"):
                    continue

                accn = accns[i] if i < len(accns) else ""
                if not accn or pd.isna(accn):
                    # Malformed record without accession number
                    continue

                accn_str = str(accn).strip()
                if accn_str in seen_accessions:
                    # Deduplicate: prevent duplicate events across files
                    continue
                seen_accessions.add(accn_str)

                filing_date = str(filed_dates[i]).strip() if i < len(filed_dates) and pd.notna(filed_dates[i]) else ""
                if start_date and filing_date and filing_date < start_date:
                    continue
                if end_date and filing_date and filing_date > end_date:
                    continue

                # Parse acceptance timestamp strictly without using filingDate as fallback
                accept_dt = acceptance_dts[i] if i < len(acceptance_dts) else None
                if accept_dt and pd.notna(accept_dt) and str(accept_dt).strip():
                    try:
                        ts = pd.to_datetime(accept_dt, utc=True)
                        data_status = "eligible"
                    except Exception:
                        ts = pd.NaT
                        data_status = "malformed_timestamp"
                else:
                    ts = pd.NaT
                    data_status = "missing_timestamp"

                # Parse items
                raw_item_val = items_raw[i] if i < len(items_raw) else None
                parsed_items = self.parse_items(raw_item_val)
                items_str = ",".join(parsed_items)

                primary_doc = str(primary_docs[i]).strip() if i < len(primary_docs) and pd.notna(primary_docs[i]) else ""
                accn_no_hyphen = accn_str.replace("-", "")
                cik_int = int(cik_clean) if cik_clean.isdigit() else 0
                filing_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accn_no_hyphen}/{primary_doc}" if primary_doc else ""

                rows.append({
                    "company_id": company_info["company_id"],
                    "cik": cik_clean,
                    "ticker": company_info["ticker"],
                    "form": form,
                    "filing_date": filing_date,
                    "acceptance_timestamp": ts,
                    "accession_number": accn_str,
                    "items": items_str,
                    "item_list": parsed_items,
                    "primary_document": primary_doc,
                    "filing_url": filing_url,
                    "is_amendment": (form == "8-K/A"),
                    "data_availability_status": data_status,
                    "parsing_status": "success",
                    "source": "sec_edgar_submissions",
                    # Priority item indicators
                    "has_item_1_01": "1.01" in parsed_items,
                    "has_item_2_02": "2.02" in parsed_items,
                    "has_item_5_02": "5.02" in parsed_items,
                    "has_item_7_01": "7.01" in parsed_items,
                    "has_item_8_01": "8.01" in parsed_items,
                })

        if not rows:
            empty_cols = [
                "company_id", "cik", "ticker", "form", "filing_date", "acceptance_timestamp",
                "accession_number", "items", "item_list", "primary_document", "filing_url",
                "is_amendment", "data_availability_status", "parsing_status", "source",
                "has_item_1_01", "has_item_2_02", "has_item_5_02", "has_item_7_01", "has_item_8_01"
            ]
            return pd.DataFrame(columns=empty_cols)

        df = pd.DataFrame(rows)
        # Sort chronologically by acceptance_timestamp or filing_date
        if df["acceptance_timestamp"].notna().any():
            df = df.sort_values(by=["acceptance_timestamp", "filing_date"]).reset_index(drop=True)
        else:
            df = df.sort_values(by="filing_date").reset_index(drop=True)
        return df



"""
SEC EDGAR Data Quality and Point-in-Time Validator.

Validates SEC financial facts and 8-K filings for schema conformance,
identifier validity, and strict point-in-time temporal integrity.
"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Any
import pandas as pd

logger = logging.getLogger(__name__)


class SECValidator:
    """Validates processed SEC EDGAR Parquet datasets."""

    @staticmethod
    def validate_facts_dataframe(df: pd.DataFrame) -> Dict[str, Any]:
        """Validates processed financial facts DataFrame."""
        report = {
            "is_valid": True,
            "total_records": len(df),
            "errors": [],
            "warnings": [],
            "metrics": {},
        }

        if df.empty:
            report["is_valid"] = False
            report["errors"].append("Dataset is empty (0 records).")
            return report

        # 1. Required columns
        required_cols = [
            "company_id", "cik", "ticker", "taxonomy", "concept", "label",
            "period_end", "form", "filed_date", "acceptance_timestamp",
            "accession_number", "value", "unit", "source"
        ]
        missing_cols = [c for c in required_cols if c not in df.columns]
        if missing_cols:
            report["is_valid"] = False
            report["errors"].append(f"Missing required columns: {missing_cols}")
            return report

        # 2. Null checks on critical fields
        critical_cols = [
            "company_id", "cik", "concept", "period_end", "form",
            "filed_date", "acceptance_timestamp", "accession_number", "value"
        ]
        null_counts = {c: int(df[c].isna().sum()) for c in critical_cols}
        report["metrics"]["null_counts"] = null_counts
        for c, count in null_counts.items():
            if count > 0:
                report["is_valid"] = False
                report["errors"].append(f"Found {count} null values in critical column '{c}'.")

        # 3. CIK format verification (10 digits)
        invalid_ciks = df[~df["cik"].str.match(r"^\d{10}$", na=False)]
        if not invalid_ciks.empty:
            report["is_valid"] = False
            report["errors"].append(f"Found {len(invalid_ciks)} records with invalid CIK format (must be 10 digits).")

        # 4. Accession number format check (e.g. 0000320193-24-000006)
        invalid_accns = df[~df["accession_number"].str.match(r"^\d{10}-\d{2}-\d{6}$", na=False)]
        if not invalid_accns.empty:
            report["warnings"].append(f"Found {len(invalid_accns)} records with non-standard accession numbers.")

        # 5. Point-in-Time Temporal Consistency Checks
        # A. Fatal Look-Ahead Leakage: Filing acceptance occurs BEFORE the fiscal period ends
        # acceptance_timestamp (date portion) < period_end
        df_temp = df.copy()
        df_temp["acceptance_date"] = pd.to_datetime(df_temp["acceptance_timestamp"]).dt.strftime("%Y-%m-%d")
        
        fatal_lookahead = df_temp[df_temp["acceptance_date"] < df_temp["period_end"]]
        report["metrics"]["fatal_lookahead_records"] = len(fatal_lookahead)
        if not fatal_lookahead.empty:
            report["is_valid"] = False
            report["errors"].append(
                f"FATAL LOOK-AHEAD ERROR: Found {len(fatal_lookahead)} facts where acceptance date "
                f"precedes period_end date (e.g. {fatal_lookahead.iloc[0]['concept']} filed on "
                f"{fatal_lookahead.iloc[0]['acceptance_date']} for period ending {fatal_lookahead.iloc[0]['period_end']})."
            )

        # B. Filing Date vs Period End
        filing_before_period = df_temp[df_temp["filed_date"] < df_temp["period_end"]]
        if not filing_before_period.empty:
            report["is_valid"] = False
            report["errors"].append(
                f"Found {len(filing_before_period)} records where filed_date precedes period_end."
            )

        # 6. Duplicates on unique fact identity
        dup_subset = ["cik", "concept", "period_end", "form", "filed_date", "accession_number"]
        duplicates = int(df.duplicated(subset=dup_subset).sum())
        report["metrics"]["duplicate_facts"] = duplicates
        if duplicates > 0:
            report["warnings"].append(f"Found {duplicates} duplicate fact records.")

        # 7. Coverage metrics
        report["metrics"]["unique_ciks"] = int(df["cik"].nunique())
        report["metrics"]["unique_companies"] = int(df["company_id"].nunique())
        report["metrics"]["unique_concepts"] = int(df["concept"].nunique())
        report["metrics"]["min_period_end"] = str(df["period_end"].min())
        report["metrics"]["max_period_end"] = str(df["period_end"].max())
        report["metrics"]["total_facts"] = len(df)

        return report

    @staticmethod
    def validate_8k_dataframe(df: pd.DataFrame) -> Dict[str, Any]:
        """Validates processed Form 8-K DataFrame."""
        report = {
            "is_valid": True,
            "total_records": len(df),
            "errors": [],
            "warnings": [],
            "metrics": {},
        }

        if df.empty:
            report["is_valid"] = False
            report["errors"].append("8-K Dataset is empty (0 records).")
            return report

        required_cols = [
            "company_id", "cik", "ticker", "form", "filing_date",
            "acceptance_timestamp", "accession_number", "items", "filing_url", "source"
        ]
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            report["is_valid"] = False
            report["errors"].append(f"Missing required 8-K columns: {missing}")
            return report

        null_critical = df[["cik", "filing_date", "acceptance_timestamp", "accession_number"]].isna().sum()
        for c, count in null_critical.items():
            if count > 0:
                report["is_valid"] = False
                report["errors"].append(f"Found {count} nulls in critical column '{c}'.")

        report["metrics"]["unique_ciks"] = int(df["cik"].nunique())
        report["metrics"]["total_8k_filings"] = len(df)
        report["metrics"]["min_filing_date"] = str(df["filing_date"].min())
        report["metrics"]["max_filing_date"] = str(df["filing_date"].max())
        return report

    @classmethod
    def validate_facts_parquet(cls, parquet_path: str) -> Dict[str, Any]:
        """Loads and validates a financial facts Parquet file."""
        path = Path(parquet_path)
        if not path.exists():
            return {"is_valid": False, "errors": [f"File not found: {parquet_path}"], "warnings": [], "metrics": {}}
        df = pd.read_parquet(path)
        return cls.validate_facts_dataframe(df)

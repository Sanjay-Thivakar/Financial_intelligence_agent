"""
Financial News Quality Validator.

Enforces schema conformance, checks for duplicate news IDs, missing headlines,
text body completeness, mapping status validity, and evaluates temporal precision
for processed news Parquet files.
"""

import logging
from pathlib import Path
from typing import Dict, List, Any
import pandas as pd

from src.data.news.schema import NewsMappingStatus

logger = logging.getLogger(__name__)


class NewsValidator:
    """Validates processed financial news data Parquet files."""

    @staticmethod
    def validate_dataframe(df: pd.DataFrame) -> Dict[str, Any]:
        """Runs quality checks on a news DataFrame."""
        report = {
            "is_valid": True,
            "total_records": len(df),
            "errors": [],
            "warnings": [],
            "metrics": {},
        }

        if df.empty:
            report["is_valid"] = False
            report["errors"].append("News dataset is empty (0 records).")
            return report

        # 1. Required core columns
        required_cols = [
            "news_id", "company_id", "ticker", "published_at", "published_date",
            "has_intraday_time", "headline", "article_text", "source", "url", "source_dataset"
        ]
        missing_cols = [c for c in required_cols if c not in df.columns]
        if missing_cols:
            report["is_valid"] = False
            report["errors"].append(f"Missing required news columns: {missing_cols}")
            return report

        # 2. Null checks on critical fields
        critical_fields = ["news_id", "ticker", "published_at", "published_date", "headline"]
        null_counts = {c: int(df[c].isna().sum()) for c in required_cols if c in df.columns}
        report["metrics"]["null_counts"] = null_counts

        for c in critical_fields:
            if null_counts.get(c, 0) > 0:
                report["is_valid"] = False
                report["errors"].append(f"Found {null_counts[c]} nulls in critical field '{c}'.")

        # 3. Duplicate checks
        dupes = int(df.duplicated(subset=["news_id"]).sum())
        report["metrics"]["duplicate_news_ids"] = dupes
        if dupes > 0:
            report["is_valid"] = False
            report["errors"].append(f"Found {dupes} duplicate news_id records.")

        # 4. Text completeness metrics
        empty_text_count = int(((df["article_text"].isna()) | (df["article_text"].str.strip() == "")).sum())
        empty_text_pct = round(empty_text_count / len(df) * 100, 2)
        report["metrics"]["empty_article_text_count"] = empty_text_count
        report["metrics"]["empty_article_text_pct"] = empty_text_pct
        if empty_text_pct > 50.0:
            report["warnings"].append(
                f"High empty article text rate: {empty_text_pct}% of records have no body text (headline only)."
            )

        # 5. Temporal precision check
        intraday_count = int(df["has_intraday_time"].sum())
        intraday_pct = round(intraday_count / len(df) * 100, 2)
        report["metrics"]["intraday_timestamp_count"] = intraday_count
        report["metrics"]["intraday_timestamp_pct"] = intraday_pct
        if intraday_pct < 50.0:
            report["warnings"].append(
                f"Low intraday time precision: {100 - intraday_pct}% of records are date-only (midnight UTC default)."
            )

        # 6. Universe entity resolution rate & mapping status
        matched_companies = int(df["company_id"].notna().sum())
        matched_pct = round(matched_companies / len(df) * 100, 2)
        report["metrics"]["universe_matched_count"] = matched_companies
        report["metrics"]["universe_matched_pct"] = matched_pct

        if "mapping_status" in df.columns:
            valid_statuses = {s.value for s in NewsMappingStatus}
            invalid_statuses = set(df["mapping_status"].dropna().unique()) - valid_statuses
            if invalid_statuses:
                report["is_valid"] = False
                report["errors"].append(f"Invalid mapping_status values detected: {invalid_statuses}")
            report["metrics"]["mapping_status_breakdown"] = df["mapping_status"].value_counts().to_dict()

        # 7. Coverage metrics
        report["metrics"]["min_date"] = str(df["published_date"].min())
        report["metrics"]["max_date"] = str(df["published_date"].max())
        report["metrics"]["unique_tickers"] = int(df["ticker"].nunique())
        report["metrics"]["unique_sources"] = int(df["source"].nunique())

        return report

    @classmethod
    def validate_parquet(cls, parquet_path: str) -> Dict[str, Any]:
        """Loads and validates a news Parquet file."""
        path = Path(parquet_path)
        if not path.exists():
            return {
                "is_valid": False,
                "total_records": 0,
                "errors": [f"File does not exist: {parquet_path}"],
                "warnings": [],
                "metrics": {},
            }
        df = pd.read_parquet(path)
        return cls.validate_dataframe(df)

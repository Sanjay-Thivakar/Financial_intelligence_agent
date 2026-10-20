"""
Exporter module for S&P 500 company universe.

Saves processed canonical tables to CSV and Parquet with strict type casting,
and outputs data quality reports in JSON and Markdown.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from src.data.universe.validator import ValidationReport

logger = logging.getLogger(__name__)


class UniverseExporter:
    """Exports processed S&P 500 universe tables and data quality reports."""

    def __init__(self, processed_dir: str | Path = "data/processed/universe"):
        self.processed_dir = Path(processed_dir)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    def export(
        self,
        universe_df: pd.DataFrame,
        report: Optional[ValidationReport] = None,
    ) -> dict[str, Path]:
        """Export universe DataFrame to CSV and Parquet, and write validation artifacts.

        Returns dictionary of exported file paths.
        """
        output_files: dict[str, Path] = {}

        # Ensure correct string types
        clean_df = universe_df.copy()
        for col in ["company_id", "ticker", "company_name"]:
            clean_df[col] = clean_df[col].astype(str)

        # Allow nullable strings for cik and sector
        clean_df["cik"] = clean_df["cik"].apply(lambda x: str(x) if pd.notna(x) and x is not None else None)
        clean_df["sector"] = clean_df["sector"].apply(lambda x: str(x) if pd.notna(x) and x is not None else None)
        clean_df["effective_to"] = clean_df["effective_to"].apply(
            lambda x: str(x) if pd.notna(x) and x is not None else None
        )

        # 1. Export CSV
        csv_path = self.processed_dir / "sp500_universe.csv"
        clean_df.to_csv(csv_path, index=False)
        output_files["csv"] = csv_path
        logger.info(f"Exported universe CSV: {csv_path} ({len(clean_df):,} rows)")

        # 2. Export Parquet
        parquet_path = self.processed_dir / "sp500_universe.parquet"
        clean_df.to_parquet(parquet_path, index=False, engine="pyarrow")
        output_files["parquet"] = parquet_path
        logger.info(f"Exported universe Parquet: {parquet_path}")

        # 3. Export Validation Report if provided
        if report:
            json_path = self.processed_dir / "universe_data_quality_report.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(report.to_dict(), f, indent=2)
            output_files["report_json"] = json_path

            md_path = self.processed_dir / "universe_data_quality_report.md"
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(report.to_markdown())
            output_files["report_md"] = md_path
            logger.info(f"Exported validation reports: {json_path}, {md_path}")

        return output_files

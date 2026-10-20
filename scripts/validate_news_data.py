"""
CLI Script to Validate Processed Financial News Parquet files.
"""

import sys
import argparse
import json
import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.news.validator import NewsValidator

logger = logging.getLogger("validate_news")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def main():
    parser = argparse.ArgumentParser(description="Validate Financial News Data Parquet files")
    parser.add_argument(
        "--file",
        type=str,
        default="data/processed/news/fnspid_news_processed.parquet",
        help="Path to news parquet file",
    )
    args = parser.parse_args()

    target_path = Path(args.file)
    logger.info(f"Validating news data file: {target_path}")

    report = NewsValidator.validate_parquet(str(target_path))

    print("\n=== FINANCIAL NEWS DATA VALIDATION REPORT ===")
    print(f"File: {target_path}")
    print(f"Status: {'PASSED' if report['is_valid'] else 'FAILED'}")
    print(f"Total Records: {report['total_records']:,}")

    if report["metrics"]:
        print("\n--- Key Metrics ---")
        for k, v in report["metrics"].items():
            print(f"  {k}: {v}")

    if report["warnings"]:
        print("\n--- Warnings ---")
        for w in report["warnings"]:
            print(f"  [WARN] {w}")

    if report["errors"]:
        print("\n--- Errors ---")
        for e in report["errors"]:
            print(f"  [ERROR] {e}")

    # Output JSON report
    report_json_path = target_path.parent / f"{target_path.stem}_validation_report.json"
    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    logger.info(f"Validation report saved to {report_json_path}")

    if not report["is_valid"]:
        sys.exit(1)


if __name__ == "__main__":
    main()

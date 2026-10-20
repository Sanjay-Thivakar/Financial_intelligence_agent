"""
CLI Script to validate existing S&P 500 company universe outputs.

Usage:
    python scripts/validate_universe.py [--file data/processed/universe/sp500_universe.parquet]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.universe.validator import UniverseValidator


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate processed S&P 500 universe file.")
    parser.add_argument(
        "--file",
        type=str,
        default="data/processed/universe/sp500_universe.parquet",
        help="Path to CSV or Parquet universe file.",
    )
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        # Fallback to CSV if parquet does not exist
        csv_fallback = file_path.with_suffix(".csv")
        if csv_fallback.exists():
            file_path = csv_fallback
        else:
            print(f"Error: file not found: {file_path}")
            return 1

    print(f"Loading universe from: {file_path}")
    if file_path.suffix == ".parquet":
        df = pd.read_parquet(file_path)
    else:
        df = pd.read_csv(file_path)

    validator = UniverseValidator(df)
    report = validator.validate()

    print("\n" + report.to_markdown())

    if report.status == "FAILED":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

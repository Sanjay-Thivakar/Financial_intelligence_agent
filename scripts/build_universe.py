"""
CLI Script to build the S&P 500 company universe and company-identity layer.

Usage:
    python scripts/build_universe.py [--fetch] [--raw-dir data/raw/universe] [--processed-dir data/processed/universe]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.universe.builder import UniverseBuilder
from src.data.universe.exporter import UniverseExporter
from src.data.universe.fetcher import RawDataFetcher
from src.data.universe.validator import UniverseValidator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("build_universe")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build S&P 500 company universe and company-identity layer."
    )
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="Force re-fetching raw data from remote sources.",
    )
    parser.add_argument(
        "--raw-dir",
        type=str,
        default="data/raw/universe",
        help="Directory to read/store raw data.",
    )
    parser.add_argument(
        "--processed-dir",
        type=str,
        default="data/processed/universe",
        help="Directory to store processed outputs.",
    )

    args = parser.parse_args()

    raw_path = Path(args.raw_dir)
    processed_path = Path(args.processed_dir)

    print("=" * 70)
    print(" S&P 500 Universe & Company-Identity Layer Builder (Phase 1)")
    print("=" * 70)

    # 1. Fetch raw data if requested or missing
    fetcher = RawDataFetcher(raw_dir=raw_path)
    if args.fetch or not (raw_path / "sp500_ticker_start_end_raw.csv").exists():
        logger.info("Fetching raw data sources...")
        fetcher.fetch_all(force=args.fetch)
    else:
        logger.info(f"Using cached raw datasets from {raw_path}")

    # 2. Build canonical universe
    logger.info("Building canonical company universe...")
    builder = UniverseBuilder(raw_dir=raw_path)
    universe_df = builder.build_canonical_universe()

    # 3. Validate universe
    logger.info("Running validation checks...")
    validator = UniverseValidator(universe_df)
    report = validator.validate()

    # 4. Export artifacts
    logger.info("Exporting processed tables and quality reports...")
    exporter = UniverseExporter(processed_dir=processed_path)
    outputs = exporter.export(universe_df, report=report)

    # 5. Print summary
    print("\n" + "=" * 70)
    print(" UNIVERSE GENERATION SUMMARY")
    print("=" * 70)
    print(f"Total Membership Records:     {report.total_records:,}")
    print(f"Unique Point-in-Time Tickers: {report.total_unique_tickers:,}")
    print(f"Canonical Companies:          {report.total_unique_companies:,}")
    print(f"Active Constituents (Today):  {report.active_constituents_count:,}")
    print(f"Resolved CIKs:                {report.resolved_cik_count:,} ({report.resolved_cik_count/report.total_records:.1%})")
    print(f"Missing CIKs (Historical):   {report.missing_cik_count:,} ({report.missing_cik_count/report.total_records:.1%})")
    print(f"Duplicate Company Records:    {report.duplicate_companies_count}")
    print(f"Invalid Tickers:              {report.invalid_tickers_count}")
    print(f"Overlapping Intervals:        {report.overlapping_intervals_count}")
    print(f"Dual-Class Active CIKs:       {report.duplicate_active_ciks_count}")
    print(f"Overall Validation Status:    {report.status}")
    print("-" * 70)
    print("Exported Files:")
    for name, path in outputs.items():
        print(f"  [{name.upper()}] {path}")
    print("=" * 70)

    if report.status == "FAILED":
        logger.error("Universe validation failed with errors.")
        return 1

    logger.info("Universe build completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

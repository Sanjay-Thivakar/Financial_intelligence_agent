"""
Market Data Quality Validator.

Enforces schema conformance, checks for price anomalies, volume anomalies,
temporal continuity, and duplicate detection on processed market Parquet files.
"""

import logging
from pathlib import Path
from typing import Dict, List, Any
import pandas as pd

logger = logging.getLogger(__name__)


# Official US equity market holiday calendar (NYSE / NASDAQ) 2018-2026
US_MARKET_HOLIDAYS = {
    # 2018
    "2018-01-01", "2018-01-15", "2018-02-19", "2018-03-30", "2018-05-28",
    "2018-07-04", "2018-09-03", "2018-11-22", "2018-12-05", "2018-12-25",
    # 2019
    "2019-01-01", "2019-01-21", "2019-02-18", "2019-04-19", "2019-05-27",
    "2019-07-04", "2019-09-02", "2019-11-28", "2019-12-25",
    # 2020
    "2020-01-01", "2020-01-20", "2020-02-17", "2020-04-10", "2020-05-25",
    "2020-07-03", "2020-09-07", "2020-11-26", "2020-12-25",
    # 2021
    "2021-01-01", "2021-01-18", "2021-02-15", "2021-04-02", "2021-05-31",
    "2021-07-05", "2021-09-06", "2021-11-25", "2021-12-24",
    # 2022
    "2022-01-17", "2022-02-21", "2022-04-15", "2022-05-30", "2022-06-20",
    "2022-07-04", "2022-09-05", "2022-11-24", "2022-12-26",
    # 2023
    "2023-01-02", "2023-01-16", "2023-02-20", "2023-04-07", "2023-05-29",
    "2023-06-19", "2023-07-04", "2023-09-04", "2023-11-23", "2023-12-25",
    # 2024
    "2024-01-01", "2024-01-15", "2024-02-19", "2024-03-29", "2024-05-27",
    "2024-06-19", "2024-07-04", "2024-09-02", "2024-11-28", "2024-12-25",
    # 2025
    "2025-01-01", "2025-01-20", "2025-02-17", "2025-04-18", "2025-05-26",
    "2025-06-19", "2025-07-04", "2025-09-01", "2025-11-27", "2025-12-25",
    # 2026
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
    "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
}


class MarketValidator:
    """Validates processed market data Parquet files."""


    @staticmethod
    def validate_dataframe(df: pd.DataFrame) -> Dict[str, Any]:
        """Runs quality checks on a market DataFrame."""
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
            "company_id", "ticker", "timestamp", "trading_date",
            "open", "high", "low", "close", "adjusted_close", "volume", "source"
        ]
        missing_cols = [c for c in required_cols if c not in df.columns]
        if missing_cols:
            report["is_valid"] = False
            report["errors"].append(f"Missing required columns: {missing_cols}")
            return report

        # 2. Null checks
        null_counts = {c: int(df[c].isna().sum()) for c in required_cols}
        report["metrics"]["null_counts"] = null_counts
        critical_nulls = ["ticker", "timestamp", "close", "volume"]
        for c in critical_nulls:
            if null_counts[c] > 0:
                report["is_valid"] = False
                report["errors"].append(f"Found {null_counts[c]} nulls in critical column '{c}'.")

        # 3. Duplicate checks
        duplicates = int(df.duplicated(subset=["ticker", "trading_date"]).sum())
        report["metrics"]["duplicate_rows"] = duplicates
        if duplicates > 0:
            report["is_valid"] = False
            report["errors"].append(f"Found {duplicates} duplicate (ticker, trading_date) records.")

        # 4. Price anomaly checks
        negative_prices = int(((df["open"] <= 0) | (df["high"] <= 0) | (df["low"] <= 0) | (df["close"] <= 0)).sum())
        report["metrics"]["non_positive_prices"] = negative_prices
        if negative_prices > 0:
            report["is_valid"] = False
            report["errors"].append(f"Found {negative_prices} non-positive price values.")

        high_low_inversion = int((df["high"] < df["low"]).sum())
        report["metrics"]["high_low_inversions"] = high_low_inversion
        if high_low_inversion > 0:
            report["is_valid"] = False
            report["errors"].append(f"Found {high_low_inversion} rows where high < low.")

        open_out_of_bounds = int(((df["open"] > df["high"] * 1.0001) | (df["open"] < df["low"] * 0.9999)).sum())
        close_out_of_bounds = int(((df["close"] > df["high"] * 1.0001) | (df["close"] < df["low"] * 0.9999)).sum())
        if open_out_of_bounds > 0:
            report["warnings"].append(f"Found {open_out_of_bounds} rows where open is outside [low, high].")
        if close_out_of_bounds > 0:
            report["warnings"].append(f"Found {close_out_of_bounds} rows where close is outside [low, high].")

        # 5. Volume checks
        neg_volume = int((df["volume"] < 0).sum())
        report["metrics"]["negative_volume"] = neg_volume
        if neg_volume > 0:
            report["is_valid"] = False
            report["errors"].append(f"Found {neg_volume} negative volume rows.")

        # 6. Corporate Action & Price Jump Checks (if extended schema present)
        if "split_factor" in df.columns:
            invalid_splits = int(((df["split_factor"] <= 0) | (df["split_factor"].isna())).sum())
            if invalid_splits > 0:
                report["is_valid"] = False
                report["errors"].append(f"Found {invalid_splits} invalid split_factor records (must be > 0).")

            # Check for unexplained price jumps (> 50% shift without split_factor != 1.0)
            df_sorted = df.sort_values(by=["ticker", "trading_date"])
            for t, grp in df_sorted.groupby("ticker"):
                if len(grp) > 1:
                    pct_change = grp["close"].pct_change().abs()
                    unexplained_jumps = grp[(pct_change > 0.50) & (grp["split_factor"] == 1.0)]
                    if not unexplained_jumps.empty:
                        report["warnings"].append(
                            f"Ticker {t} has {len(unexplained_jumps)} price changes >50% without recorded split factor."
                        )

        if "dividend_cash" in df.columns:
            neg_divs = int((df["dividend_cash"] < 0).sum())
            if neg_divs > 0:
                report["is_valid"] = False
                report["errors"].append(f"Found {neg_divs} negative dividend_cash records.")

        # 7. Date range metrics
        report["metrics"]["min_date"] = str(df["trading_date"].min())
        report["metrics"]["max_date"] = str(df["trading_date"].max())
        report["metrics"]["unique_tickers"] = int(df["ticker"].nunique())
        report["metrics"]["unique_companies"] = int(df["company_id"].nunique())

        return report

    @staticmethod
    def calculate_session_coverage(
        actual_dates: List[str],
        start_date: str,
        end_date: str,
    ) -> Dict[str, Any]:
        """
        Calculates expected trading sessions vs observed sessions,
        excluding weekends and official US equity exchange holidays.
        """
        all_business_days = [
            d.strftime("%Y-%m-%d") for d in pd.date_range(start=start_date, end=end_date, freq="B")
        ]
        expected_trading_days = [
            d for d in all_business_days if d not in US_MARKET_HOLIDAYS
        ]
        expected_set = set(expected_trading_days)
        actual_set = set(actual_dates)

        observed_valid = actual_set & expected_set
        missing_sessions = sorted(list(expected_set - actual_set))
        unexpected_sessions = sorted(list(actual_set - expected_set))

        expected_count = len(expected_set)
        observed_count = len(observed_valid)
        coverage_pct = round(observed_count / max(expected_count, 1) * 100, 2)

        return {
            "expected_business_days": len(all_business_days),
            "exchange_holidays": len(all_business_days) - expected_count,
            "expected_sessions": expected_count,
            "observed_sessions": observed_count,
            "missing_sessions": missing_sessions,
            "missing_count": len(missing_sessions),
            "unexpected_sessions": unexpected_sessions,
            "coverage_pct": coverage_pct,
        }

    @classmethod
    def validate_parquet(cls, parquet_path: str) -> Dict[str, Any]:
        """Loads and validates a market Parquet file."""
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

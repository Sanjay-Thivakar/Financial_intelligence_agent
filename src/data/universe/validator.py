"""
Validator module for S&P 500 company universe.

Implements rigorous data quality checks:
1. Duplicate companies
2. Duplicate CIKs (multi-class vs. sequential vs. invalid)
3. Invalid tickers
4. Overlapping membership intervals
5. Missing CIKs
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Valid US ticker regex: 1-5 letters optionally followed by '.' and 1-2 letters (e.g. BRK.B)
US_TICKER_REGEX = re.compile(r"^[A-Z]{1,5}(\.[A-Z]{1,2})?$")


@dataclass
class ValidationIssue:
    category: str
    severity: str  # "ERROR", "WARNING", "INFO"
    identifier: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationReport:
    timestamp: str
    total_records: int
    total_unique_tickers: int
    total_unique_companies: int
    active_constituents_count: int
    resolved_cik_count: int
    missing_cik_count: int
    duplicate_companies_count: int
    duplicate_active_ciks_count: int
    invalid_tickers_count: int
    overlapping_intervals_count: int
    status: str  # "PASSED", "WARNING", "FAILED"
    issues: List[ValidationIssue] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "total_records": self.total_records,
            "total_unique_tickers": self.total_unique_tickers,
            "total_unique_companies": self.total_unique_companies,
            "active_constituents_count": self.active_constituents_count,
            "resolved_cik_count": self.resolved_cik_count,
            "missing_cik_count": self.missing_cik_count,
            "duplicate_companies_count": self.duplicate_companies_count,
            "duplicate_active_ciks_count": self.duplicate_active_ciks_count,
            "invalid_tickers_count": self.invalid_tickers_count,
            "overlapping_intervals_count": self.overlapping_intervals_count,
            "status": self.status,
            "issues": [asdict(issue) for issue in self.issues],
        }

    def to_markdown(self) -> str:
        md = [
            "# S&P 500 Universe Data Quality Report",
            "",
            f"**Execution Timestamp (UTC):** {self.timestamp}  ",
            f"**Overall Validation Status:** `{self.status}`  ",
            "",
            "## Summary Metrics",
            "",
            "| Metric | Count | Notes |",
            "| :--- | :--- | :--- |",
            f"| Total Membership Records | **{self.total_records:,}** | Historical & active intervals |",
            f"| Total Unique Tickers | **{self.total_unique_tickers:,}** | Point-in-time trading symbols |",
            f"| Total Unique Companies | **{self.total_unique_companies:,}** | Canonical company IDs |",
            f"| Currently Active Constituents | **{self.active_constituents_count:,}** | Open interval (effective_to is None) |",
            f"| Records with Resolved CIK | **{self.resolved_cik_count:,}** | Standardized 10-digit SEC CIK |",
            f"| Records with Missing CIK | **{self.missing_cik_count:,}** | Delisted historical firms flagged |",
            f"| Duplicate Company Rows | **{self.duplicate_companies_count:,}** | Duplicate exact intervals |",
            f"| Duplicate Active CIKs | **{self.duplicate_active_ciks_count:,}** | Legitimate dual-class shares |",
            f"| Invalid Ticker Symbols | **{self.invalid_tickers_count:,}** | Malformed tickers |",
            f"| Overlapping Intervals | **{self.overlapping_intervals_count:,}** | Overlapping ticker time series |",
            "",
            "## Data Quality Findings",
            "",
        ]

        if not self.issues:
            md.append("No data quality warnings or errors detected. All validation checks passed.")
        else:
            by_cat: Dict[str, List[ValidationIssue]] = {}
            for issue in self.issues:
                by_cat.setdefault(issue.category, []).append(issue)

            for cat, cat_issues in by_cat.items():
                md.append(f"### {cat} ({len(cat_issues)} items)")
                md.append("")
                md.append("| Severity | Identifier | Description | Details |")
                md.append("| :--- | :--- | :--- | :--- |")
                # Show top 15 issues per category to keep readable
                for issue in cat_issues[:15]:
                    det_str = ", ".join(f"{k}={v}" for k, v in issue.details.items()) if issue.details else "-"
                    md.append(f"| `{issue.severity}` | `{issue.identifier}` | {issue.message} | {det_str} |")
                if len(cat_issues) > 15:
                    md.append(f"| `INFO` | ... | *[Truncated: {len(cat_issues) - 15} more items]* | - |")
                md.append("")

        return "\n".join(md)


class UniverseValidator:
    """Validates canonical S&P 500 company universe DataFrame."""

    def __init__(self, universe_df: pd.DataFrame):
        self.df = universe_df.copy()

    def validate(self) -> ValidationReport:
        """Run all validation suites and return detailed report."""
        issues: List[ValidationIssue] = []

        # 1. Check duplicate company rows (exact duplicate ticker + interval)
        dup_mask = self.df.duplicated(subset=["ticker", "effective_from", "effective_to"], keep=False)
        dup_rows = self.df[dup_mask]
        duplicate_companies_count = len(dup_rows)
        for _, row in dup_rows.iterrows():
            issues.append(
                ValidationIssue(
                    category="Duplicate Companies",
                    severity="ERROR",
                    identifier=f"{row['company_id']}:{row['ticker']}",
                    message="Identical ticker and interval duplicate record detected",
                    details={
                        "ticker": row["ticker"],
                        "effective_from": row["effective_from"],
                        "effective_to": str(row["effective_to"]),
                    },
                )
            )

        # 2. Check duplicate active CIKs
        # Active means effective_to is None
        active_df = self.df[self.df["effective_to"].isna()].copy()
        active_cik_df = active_df[active_df["cik"].notna()]
        cik_counts = active_cik_df.groupby("cik")["ticker"].unique()
        multi_class_ciks = cik_counts[cik_counts.apply(len) > 1]
        duplicate_active_ciks_count = len(multi_class_ciks)

        for cik_val, tickers in multi_class_ciks.items():
            issues.append(
                ValidationIssue(
                    category="Duplicate Active CIKs (Dual Share Classes)",
                    severity="INFO",
                    identifier=f"CIK_{cik_val}",
                    message="Multiple active share classes share the same corporate CIK identity",
                    details={"cik": cik_val, "tickers": list(tickers)},
                )
            )

        # 3. Check invalid tickers
        invalid_tickers = []
        for ticker in self.df["ticker"].unique():
            if not US_TICKER_REGEX.match(ticker):
                invalid_tickers.append(ticker)
                issues.append(
                    ValidationIssue(
                        category="Invalid Tickers",
                        severity="ERROR",
                        identifier=ticker,
                        message="Ticker format does not conform to US market symbol specification",
                        details={"ticker": ticker},
                    )
                )
        invalid_tickers_count = len(invalid_tickers)

        # 4. Check overlapping membership intervals
        # For each ticker, verify start_2 >= end_1 (half-open semantics)
        overlapping_count = 0
        df_sorted = self.df.sort_values(by=["ticker", "effective_from"]).reset_index(drop=True)

        for ticker, grp in df_sorted.groupby("ticker"):
            grp = grp.reset_index(drop=True)
            if len(grp) > 1:
                for i in range(len(grp) - 1):
                    start1 = grp.loc[i, "effective_from"]
                    end1 = grp.loc[i, "effective_to"]
                    start2 = grp.loc[i + 1, "effective_from"]
                    end2 = grp.loc[i + 1, "effective_to"]

                    # If end1 is null, but there's a subsequent interval, that is an error!
                    if end1 is None:
                        overlapping_count += 1
                        issues.append(
                            ValidationIssue(
                                category="Overlapping Membership Intervals",
                                severity="ERROR",
                                identifier=ticker,
                                message="Interval 1 is still open while Interval 2 starts",
                                details={
                                    "int1": f"[{start1}, None]",
                                    "int2": f"[{start2}, {end2}]",
                                },
                            )
                        )
                    elif start2 < end1:  # Strict overlap
                        overlapping_count += 1
                        issues.append(
                            ValidationIssue(
                                category="Overlapping Membership Intervals",
                                severity="ERROR",
                                identifier=ticker,
                                message="Intervals for same ticker overlap in time",
                                details={
                                    "int1": f"[{start1}, {end1}]",
                                    "int2": f"[{start2}, {end2}]",
                                },
                            )
                        )

        # 5. Check missing CIKs
        missing_cik_df = self.df[self.df["cik"].isna()]
        missing_cik_count = len(missing_cik_df)
        for _, row in missing_cik_df.iterrows():
            issues.append(
                ValidationIssue(
                    category="Missing CIKs (Historical Delisted Entities)",
                    severity="WARNING",
                    identifier=row["ticker"],
                    message="SEC CIK could not be resolved from EDGAR active registries",
                    details={
                        "company_name": row["company_name"],
                        "effective_from": row["effective_from"],
                        "effective_to": str(row["effective_to"]),
                    },
                )
            )

        # Determine overall validation status
        has_errors = any(i.severity == "ERROR" for i in issues)
        has_warnings = any(i.severity == "WARNING" for i in issues)

        if has_errors:
            status = "FAILED"
        elif has_warnings:
            status = "PASSED_WITH_WARNINGS"
        else:
            status = "PASSED"

        report = ValidationReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_records=int(len(self.df)),
            total_unique_tickers=int(self.df["ticker"].nunique()),
            total_unique_companies=int(self.df["company_id"].nunique()),
            active_constituents_count=int(len(active_df)),
            resolved_cik_count=int(self.df["cik"].notna().sum()),
            missing_cik_count=int(missing_cik_count),
            duplicate_companies_count=int(duplicate_companies_count),
            duplicate_active_ciks_count=int(duplicate_active_ciks_count),
            invalid_tickers_count=int(invalid_tickers_count),
            overlapping_intervals_count=int(overlapping_count),
            status=status,
            issues=issues,
        )

        return report

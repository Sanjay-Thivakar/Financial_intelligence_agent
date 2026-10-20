"""
Unit and integration tests for S&P 500 company universe and identity layer.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.data.universe.builder import UniverseBuilder
from src.data.universe.ticker_mapping import (
    format_cik,
    generate_company_id,
    normalize_ticker,
)
from src.data.universe.validator import UniverseValidator


def test_normalize_ticker():
    assert normalize_ticker("BRK-B") == "BRK.B"
    assert normalize_ticker("BF-B") == "BF.B"
    assert normalize_ticker("aapl ") == "AAPL"
    assert normalize_ticker("msft") == "MSFT"
    assert normalize_ticker("RDS/A") == "RDS.A"


def test_format_cik():
    assert format_cik(320193) == "0000320193"
    assert format_cik("320193") == "0000320193"
    assert format_cik("320193.0") == "0000320193"
    assert format_cik(1045810) == "0001045810"
    assert format_cik(None) is None
    assert format_cik("nan") is None
    assert format_cik("0") is None
    assert format_cik("") is None


def test_generate_company_id():
    assert generate_company_id("0000320193", "Apple Inc.", "AAPL") == "US_CIK_0000320193"
    assert generate_company_id(None, "Unknown Old Co", "OLD") == "COMP_NO_CIK_OLD"


def test_universe_builder_schema():
    builder = UniverseBuilder()
    df = builder.build_canonical_universe()

    expected_cols = [
        "company_id",
        "ticker",
        "cik",
        "company_name",
        "sector",
        "effective_from",
        "effective_to",
    ]
    assert list(df.columns) == expected_cols
    assert len(df) > 1000
    assert df["effective_to"].isna().sum() == 503  # Current S&P 500 membership size


def test_point_in_time_query():
    builder = UniverseBuilder()
    df = builder.build_canonical_universe()

    # In 2018: FB must be in index, META must not be
    as_of_2018 = builder.get_constituents_at_date(df, "2018-01-01")
    symbols_2018 = set(as_of_2018["ticker"])
    assert "FB" in symbols_2018
    assert "META" not in symbols_2018

    # In 2023: META must be in index, FB must not be
    as_of_2023 = builder.get_constituents_at_date(df, "2023-01-01")
    symbols_2023 = set(as_of_2023["ticker"])
    assert "META" in symbols_2023
    assert "FB" not in symbols_2023

    # Lehman Brothers (LEHMQ) was in index in 2005, but not in 2020
    as_of_2005 = builder.get_constituents_at_date(df, "2005-01-01")
    symbols_2005 = set(as_of_2005["ticker"])
    assert "LEHMQ" in symbols_2005

    as_of_2020 = builder.get_constituents_at_date(df, "2020-01-01")
    symbols_2020 = set(as_of_2020["ticker"])
    assert "LEHMQ" not in symbols_2020


def test_validator_detects_deliberate_errors():
    bad_df = pd.DataFrame([
        {
            "company_id": "US_CIK_0000000001",
            "ticker": "TEST$BAD",  # Invalid ticker
            "cik": "0000000001",
            "company_name": "Test Bad Corp",
            "sector": "Information Technology",
            "effective_from": "2020-01-01",
            "effective_to": "2021-01-01",
        },
        {
            "company_id": "US_CIK_0000000002",
            "ticker": "AAPL",
            "cik": "0000000002",
            "company_name": "Apple Dup 1",
            "sector": "Information Technology",
            "effective_from": "2020-01-01",
            "effective_to": "2022-01-01",
        },
        {
            "company_id": "US_CIK_0000000002",
            "ticker": "AAPL",
            "cik": "0000000002",
            "company_name": "Apple Dup 2",
            "sector": "Information Technology",
            "effective_from": "2021-06-01",  # Overlaps with 2020-01-01..2022-01-01!
            "effective_to": None,
        },
    ])

    validator = UniverseValidator(bad_df)
    report = validator.validate()
    assert report.status == "FAILED"
    assert report.invalid_tickers_count == 1
    assert report.overlapping_intervals_count == 1

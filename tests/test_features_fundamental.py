"""
Unit Tests for Fundamental Feature Engineering.

Validates point-in-time SEC EDGAR snapshotting, restatement handling,
absence of look-ahead leakage, preservation of missing facts as NaN,
and non-invention of financial ratios.
"""

import numpy as np
import pandas as pd
import pytest

from src.features.config import FundamentalFeatureConfig
from src.features.fundamental import FundamentalFeatureEngine


@pytest.fixture
def mock_sec_facts_series():
    """Generates a controlled series of SEC facts including an amendment."""
    records = [
        # 1. Q3 2023 10-Q (period_end 2023-09-30, filed & accepted 2023-11-02 18:00:00 UTC)
        {
            "company_id": "US_CIK_0000320193",
            "cik": "0000320193",
            "ticker": "AAPL",
            "concept": "Revenues",
            "label": "Revenue",
            "period_end": "2023-09-30",
            "form": "10-Q",
            "acceptance_timestamp": pd.to_datetime("2023-11-02 18:00:00", utc=True),
            "accession_number": "0000320193-23-000100",
            "value": 89500000000.0,
        },
        {
            "company_id": "US_CIK_0000320193",
            "cik": "0000320193",
            "ticker": "AAPL",
            "concept": "NetIncomeLoss",
            "label": "Net Income",
            "period_end": "2023-09-30",
            "form": "10-Q",
            "acceptance_timestamp": pd.to_datetime("2023-11-02 18:00:00", utc=True),
            "accession_number": "0000320193-23-000100",
            "value": 22950000000.0,
        },
        {
            "company_id": "US_CIK_0000320193",
            "cik": "0000320193",
            "ticker": "AAPL",
            "concept": "Assets",
            "label": "Total Assets",
            "period_end": "2023-09-30",
            "form": "10-Q",
            "acceptance_timestamp": pd.to_datetime("2023-11-02 18:00:00", utc=True),
            "accession_number": "0000320193-23-000100",
            "value": 352583000000.0,
        },
        {
            "company_id": "US_CIK_0000320193",
            "cik": "0000320193",
            "ticker": "AAPL",
            "concept": "Liabilities",
            "label": "Total Liabilities",
            "period_end": "2023-09-30",
            "form": "10-Q",
            "acceptance_timestamp": pd.to_datetime("2023-11-02 18:00:00", utc=True),
            "accession_number": "0000320193-23-000100",
            "value": 290437000000.0,
        },

        # 2. Q4/FY 2023 10-K (period_end 2023-12-30, filed & accepted 2024-02-01 18:15:30 UTC)
        {
            "company_id": "US_CIK_0000320193",
            "cik": "0000320193",
            "ticker": "AAPL",
            "concept": "Revenues",
            "label": "Revenue",
            "period_end": "2023-12-30",
            "form": "10-K",
            "acceptance_timestamp": pd.to_datetime("2024-02-01 18:15:30", utc=True),
            "accession_number": "0000320193-24-000006",
            "value": 119575000000.0,
        },
        {
            "company_id": "US_CIK_0000320193",
            "cik": "0000320193",
            "ticker": "AAPL",
            "concept": "NetIncomeLoss",
            "label": "Net Income",
            "period_end": "2023-12-30",
            "form": "10-K",
            "acceptance_timestamp": pd.to_datetime("2024-02-01 18:15:30", utc=True),
            "accession_number": "0000320193-24-000006",
            "value": 33916000000.0,
        },

        # 3. Amended 10-K/A for 2023-12-30 (filed & accepted 2024-03-15 17:00:00 UTC)
        {
            "company_id": "US_CIK_0000320193",
            "cik": "0000320193",
            "ticker": "AAPL",
            "concept": "NetIncomeLoss",
            "label": "Net Income (Restated)",
            "period_end": "2023-12-30",
            "form": "10-K/A",
            "acceptance_timestamp": pd.to_datetime("2024-03-15 17:00:00", utc=True),
            "accession_number": "0000320193-24-000020",
            "value": 34100000000.0,  # Restated upward
        },
    ]
    return pd.DataFrame(records)


class TestFundamentalFeatureEngine:
    def test_sec_filing_released_after_decision_cutoff(self, mock_sec_facts_series):
        """
        10-K was accepted on 2024-02-01 18:15:30 UTC.
        A decision on 2024-02-01 12:00:00 UTC (before filing) MUST see the Q3 2023 facts, NOT 10-K!
        A decision on 2024-02-01 19:00:00 UTC (after filing) MUST see the 10-K facts.
        """
        engine = FundamentalFeatureEngine(mock_sec_facts_series)

        # 1. Before public acceptance cutoff (e.g. at market noon)
        cutoff_before = pd.Timestamp("2024-02-01 12:00:00", tz="UTC")
        snap_before = engine.get_as_of_snapshot("US_CIK_0000320193", cutoff_before)

        assert snap_before["fundamental_available"] is True
        assert snap_before["fundamental_revenue"] == 89500000000.0
        assert snap_before["fundamental_revenue_period_end"] == "2023-09-30"
        assert snap_before["fundamental_revenue_form"] == "10-Q"
        assert snap_before["fundamental_revenue_accn"] == "0000320193-23-000100"

        # 2. After public acceptance cutoff (e.g. after market close)
        cutoff_after = pd.Timestamp("2024-02-01 19:00:00", tz="UTC")
        snap_after = engine.get_as_of_snapshot("US_CIK_0000320193", cutoff_after)

        assert snap_after["fundamental_revenue"] == 119575000000.0
        assert snap_after["fundamental_revenue_period_end"] == "2023-12-30"
        assert snap_after["fundamental_revenue_form"] == "10-K"
        assert snap_after["fundamental_revenue_accn"] == "0000320193-24-000006"

    def test_restated_fundamentals_handling(self, mock_sec_facts_series):
        """
        Original 10-K net income: 33,916,000,000 (accepted 2024-02-01).
        Amended 10-K/A net income: 34,100,000,000 (accepted 2024-03-15).
        - Before 2024-03-15: returns 33,916,000,000 (original).
        - After 2024-03-15: returns 34,100,000,000 (restated).
        """
        engine = FundamentalFeatureEngine(mock_sec_facts_series)

        # Before amendment
        cutoff_mid = pd.Timestamp("2024-03-01 12:00:00", tz="UTC")
        snap_mid = engine.get_as_of_snapshot("US_CIK_0000320193", cutoff_mid)
        assert snap_mid["fundamental_net_income"] == 33916000000.0
        assert snap_mid["fundamental_net_income_form"] == "10-K"

        # After amendment
        cutoff_post = pd.Timestamp("2024-03-20 12:00:00", tz="UTC")
        snap_post = engine.get_as_of_snapshot("US_CIK_0000320193", cutoff_post)
        assert snap_post["fundamental_net_income"] == 34100000000.0
        assert snap_post["fundamental_net_income_form"] == "10-K/A"

    def test_missing_facts_are_nan_not_zero(self, mock_sec_facts_series):
        """Operating cash flow is NOT in the mock dataset; it must be NaN with missing indicator True."""
        engine = FundamentalFeatureEngine(mock_sec_facts_series)
        cutoff = pd.Timestamp("2024-02-15 12:00:00", tz="UTC")
        snap = engine.get_as_of_snapshot("US_CIK_0000320193", cutoff)

        assert np.isnan(snap["fundamental_operating_cash_flow"])
        assert snap["fundamental_operating_cash_flow_missing"] is True
        # Must definitely NOT be 0.0
        assert snap["fundamental_operating_cash_flow"] != 0.0

    def test_ratio_computation_and_no_invention(self, mock_sec_facts_series):
        """
        Verifies ratio computation:
        - Debt-to-Assets = 290,437,000,000 / 352,583,000,000 ~ 0.8237
        - Operating Cash Flow to Net Income must be NaN (since OCF is missing) and NOT 0!
        """
        engine = FundamentalFeatureEngine(mock_sec_facts_series)
        cutoff = pd.Timestamp("2023-11-15 12:00:00", tz="UTC")
        snap = engine.get_as_of_snapshot("US_CIK_0000320193", cutoff)

        expected_debt_to_assets = 290437000000.0 / 352583000000.0
        assert pytest.approx(snap["fundamental_ratio_debt_to_assets"], rel=1e-4) == expected_debt_to_assets
        assert snap["fundamental_ratio_debt_to_assets_missing"] is False

        # OCF to Net Income cannot be computed
        assert np.isnan(snap["fundamental_ratio_ocf_to_net_income"])
        assert snap["fundamental_ratio_ocf_to_net_income_missing"] is True

    def test_unknown_company_returns_empty_snapshot(self, mock_sec_facts_series):
        engine = FundamentalFeatureEngine(mock_sec_facts_series)
        cutoff = pd.Timestamp("2024-02-15 12:00:00", tz="UTC")
        snap = engine.get_as_of_snapshot("UNKNOWN_COMPANY", cutoff)

        assert snap["fundamental_available"] is False
        assert np.isnan(snap["fundamental_revenue"])
        assert snap["fundamental_revenue_missing"] is True

    def test_concept_alias_prioritizes_most_recent_period(self):
        """
        Tests that when older facts exist under concept tag 'Revenues' (e.g. 2017)
        and newer facts exist under 'RevenueFromContractWithCustomerExcludingAssessedTax' (e.g. 2023),
        the engine picks the 2023 fact rather than getting stuck on obsolete 2017 tag.
        """
        records = [
            # Obsolete tag used in 2017
            {
                "company_id": "US_CIK_0000320193",
                "concept": "Revenues",
                "period_end": "2017-09-30",
                "form": "10-K",
                "acceptance_timestamp": pd.to_datetime("2017-11-03 17:00:00", utc=True),
                "accession_number": "0000320193-17-000070",
                "value": 229234000000.0,
            },
            # Modern ASC 606 tag used in 2023
            {
                "company_id": "US_CIK_0000320193",
                "concept": "RevenueFromContractWithCustomerExcludingAssessedTax",
                "period_end": "2023-09-30",
                "form": "10-K",
                "acceptance_timestamp": pd.to_datetime("2023-11-03 17:00:00", utc=True),
                "accession_number": "0000320193-23-000106",
                "value": 383285000000.0,
            },
        ]
        df = pd.DataFrame(records)
        engine = FundamentalFeatureEngine(df)

        cutoff = pd.Timestamp("2023-11-15 12:00:00", tz="UTC")
        snap = engine.get_as_of_snapshot("US_CIK_0000320193", cutoff)

        assert snap["fundamental_available"] is True
        # Must pick 2023 fact ($383B), NOT 2017 fact ($229B)!
        assert snap["fundamental_revenue"] == 383285000000.0
        assert snap["fundamental_revenue_period_end"] == "2023-09-30"
        assert snap["fundamental_revenue_accn"] == "0000320193-23-000106"


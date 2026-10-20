"""
Unit Tests for US Equity Exchange Calendar, Timezone Transitions, and Post-Close Filing Safety.

Validates daylight saving time transitions (EDT vs EST), early-close sessions,
weekend/holiday skipping for next-session open, and regression-tests that
post-close SEC filings are strictly excluded from same-day market close decisions.
"""

import pandas as pd
import pytest

from src.features.calendar import MarketCalendar
from src.features.config import MarketFeatureConfig, DecisionTimingMode
from src.features.market import MarketFeatureEngine
from src.features.fundamental import FundamentalFeatureEngine
from src.features.alignment import TemporalAligner


class TestMarketCalendar:
    def test_daylight_saving_market_close_utc(self):
        """
        Critical regression test:
        - During Eastern Daylight Time (EDT, UTC-4), 16:00 ET close is 20:00:00 UTC.
        - During Eastern Standard Time (EST, UTC-5), 16:00 ET close is 21:00:00 UTC.
        """
        # Summer date: 2023-05-26 (Friday before Memorial Day, EDT)
        summer_close = MarketCalendar.get_session_close_utc("2023-05-26")
        assert summer_close == pd.Timestamp("2023-05-26 20:00:00", tz="UTC")
        assert summer_close.hour == 20

        # Winter date: 2023-01-13 (Friday before MLK Day, EST)
        winter_close = MarketCalendar.get_session_close_utc("2023-01-13")
        assert winter_close == pd.Timestamp("2023-01-13 21:00:00", tz="UTC")
        assert winter_close.hour == 21

    def test_early_close_sessions_utc(self):
        """
        Official early close is 13:00 ET (1:00 PM ET).
        - Summer (EDT): 13:00 ET = 17:00:00 UTC.
        - Winter (EST): 13:00 ET = 18:00:00 UTC.
        """
        # 2023-07-03: Day before Independence Day (EDT)
        assert MarketCalendar.is_early_close("2023-07-03") is True
        july3_close = MarketCalendar.get_session_close_utc("2023-07-03")
        assert july3_close == pd.Timestamp("2023-07-03 17:00:00", tz="UTC")
        assert july3_close.hour == 17

        # 2023-11-24: Black Friday (EST)
        assert MarketCalendar.is_early_close("2023-11-24") is True
        black_friday_close = MarketCalendar.get_session_close_utc("2023-11-24")
        assert black_friday_close == pd.Timestamp("2023-11-24 18:00:00", tz="UTC")
        assert black_friday_close.hour == 18

    def test_next_session_open_skips_weekends_and_holidays(self):
        """
        Verifies NEXT_SESSION_OPEN:
        - Friday 2023-05-26: Memorial Day is Monday 2023-05-29.
          Next session is Tuesday 2023-05-30 09:30 ET = 13:30:00 UTC (EDT).
        - Friday 2023-01-13: MLK Day is Monday 2023-01-16.
          Next session is Tuesday 2023-01-17 09:30 ET = 14:30:00 UTC (EST).
        """
        # Next trading session after 2023-05-26
        next_session_summer = MarketCalendar.get_next_trading_session("2023-05-26")
        assert next_session_summer == "2023-05-30"  # Tuesday after Memorial Day!
        next_open_summer = MarketCalendar.get_next_session_open_utc("2023-05-26")
        assert next_open_summer == pd.Timestamp("2023-05-30 13:30:00", tz="UTC")

        # Next trading session after 2023-01-13
        next_session_winter = MarketCalendar.get_next_trading_session("2023-01-13")
        assert next_session_winter == "2023-01-17"  # Tuesday after MLK Day!
        next_open_winter = MarketCalendar.get_next_session_open_utc("2023-01-13")
        assert next_open_winter == pd.Timestamp("2023-01-17 14:30:00", tz="UTC")

    def test_post_close_sec_filing_strictly_excluded_from_same_close_decision(self):
        """
        Critical regression test for look-ahead leakage:
        - On 2023-05-26 (EDT), market closes at 16:00 ET = 20:00:00 UTC.
        - An SEC filing is accepted at 16:15 ET = 20:15:00 UTC (15 mins after close).
        - A decision cutoff at session close (20:00:00 UTC) MUST NOT see this filing.
        - The next session open (2023-05-30 13:30:00 UTC) DOES see this filing.
        """
        # 1. Market row for 2023-05-26
        df_market = pd.DataFrame([{
            "company_id": "US_CIK_0000320193",
            "ticker": "AAPL",
            "timestamp": pd.to_datetime("2023-05-26 00:00:00", utc=True),
            "trading_date": "2023-05-26",
            "open": 175.0, "high": 176.0, "low": 174.0, "close": 175.43,
            "adjusted_open": 175.0, "adjusted_high": 176.0, "adjusted_low": 174.0, "adjusted_close": 175.43,
            "volume": 50000000,
        }])

        # 2. SEC filing accepted at 20:15:00 UTC (16:15 Eastern, post-close)
        df_facts = pd.DataFrame([{
            "company_id": "US_CIK_0000320193",
            "concept": "Revenues",
            "period_end": "2023-03-31",
            "form": "10-Q",
            "acceptance_timestamp": pd.to_datetime("2023-05-26 20:15:00", utc=True),
            "accession_number": "0000320193-23-000099",
            "value": 94836000000.0,
        }])

        # 3. Test Mode A: MARKET_CLOSE
        engine_close = MarketFeatureEngine(MarketFeatureConfig(decision_timing=DecisionTimingMode.MARKET_CLOSE))
        df_mkt_close = engine_close.compute_features(df_market)
        # Verify decision timestamp is 20:00:00 UTC (not 21:00 UTC!)
        d_ts_close = df_mkt_close.iloc[0]["decision_timestamp"]
        assert d_ts_close == pd.Timestamp("2023-05-26 20:00:00", tz="UTC")

        # Align with fundamental engine
        fund_engine = FundamentalFeatureEngine(df_facts)
        aligner = TemporalAligner(market_engine=engine_close, fundamental_engine=fund_engine)
        aligned_close = aligner.align_features(df_market)

        # The post-close filing MUST be excluded from same-day close decision!
        assert pd.isna(aligned_close.iloc[0]["fundamental_revenue"])
        assert bool(aligned_close.iloc[0]["fundamental_revenue_missing"]) is True

        # 4. Test Mode B: NEXT_SESSION_OPEN (cutoff is Tuesday 2023-05-30 13:30:00 UTC)
        engine_open = MarketFeatureEngine(MarketFeatureConfig(decision_timing=DecisionTimingMode.NEXT_SESSION_OPEN))
        df_mkt_open = engine_open.compute_features(df_market)
        d_ts_open = df_mkt_open.iloc[0]["decision_timestamp"]
        assert d_ts_open == pd.Timestamp("2023-05-30 13:30:00", tz="UTC")

        aligner_open = TemporalAligner(market_engine=engine_open, fundamental_engine=fund_engine)
        aligned_open = aligner_open.align_features(df_market)

        # For next session open, the filing IS now legally available!
        assert aligned_open.iloc[0]["fundamental_revenue"] == 94836000000.0
        assert bool(aligned_open.iloc[0]["fundamental_revenue_missing"]) is False
        assert aligned_open.iloc[0]["fundamental_revenue_accn"] == "0000320193-23-000099"

    def test_early_close_regression(self):
        """
        Regression test for early-close detection and session close timestamps:
        - 2023-07-03 (day before July 4th, EDT): closes early at 13:00 ET = 17:00:00 UTC.
        - 2023-11-24 (Black Friday, EST): closes early at 13:00 ET = 18:00:00 UTC.
        - Regular trading days (e.g. 2023-07-05, 2023-11-27) must NOT be flagged as early close.
        """
        # Early close days
        assert MarketCalendar.is_early_close("2023-07-03") is True
        assert MarketCalendar.is_early_close("2023-11-24") is True
        assert MarketCalendar.get_session_close_utc("2023-07-03") == pd.Timestamp("2023-07-03 17:00:00", tz="UTC")
        assert MarketCalendar.get_session_close_utc("2023-11-24") == pd.Timestamp("2023-11-24 18:00:00", tz="UTC")

        # Non-early close days
        assert MarketCalendar.is_early_close("2023-07-05") is False
        assert MarketCalendar.is_early_close("2023-11-27") is False
        assert MarketCalendar.get_session_close_utc("2023-07-05") == pd.Timestamp("2023-07-05 20:00:00", tz="UTC")
        assert MarketCalendar.get_session_close_utc("2023-11-27") == pd.Timestamp("2023-11-27 21:00:00", tz="UTC")

    def test_full_day_holiday_regression(self):
        """
        Regression test for full-day holidays across regular annual holidays and historical special closures:
        - New Year's Day (observed): 2023-01-02
        - Martin Luther King Jr. Day: 2023-01-16
        - Presidents' Day: 2023-02-20
        - Good Friday: 2023-04-07
        - Memorial Day: 2023-05-29
        - Juneteenth: 2023-06-19
        - Independence Day: 2023-07-04
        - Labor Day: 2023-09-04
        - Thanksgiving Day: 2023-11-23
        - Christmas Day: 2023-12-25
        - Special Mourning Closure: 2018-12-05 (President George H.W. Bush)
        All must return is_trading_session() == False.
        """
        holidays = [
            "2023-01-02",  # New Year's Day (obs)
            "2023-01-16",  # MLK Day
            "2023-02-20",  # Presidents' Day
            "2023-04-07",  # Good Friday
            "2023-05-29",  # Memorial Day
            "2023-06-19",  # Juneteenth
            "2023-07-04",  # Independence Day
            "2023-09-04",  # Labor Day
            "2023-11-23",  # Thanksgiving Day
            "2023-12-25",  # Christmas Day
            "2018-12-05",  # George H.W. Bush Mourning Day
        ]
        for h in holidays:
            assert MarketCalendar.is_trading_session(h) is False, f"Expected {h} to be recognized as non-trading holiday"

        # A standard trading Tuesday must be active
        assert MarketCalendar.is_trading_session("2023-05-30") is True

    def test_weekend_regression(self):
        """
        Regression test for weekend rejection:
        - Saturday (weekday 5) and Sunday (weekday 6) must never be trading sessions.
        """
        weekends = [
            "2023-05-27",  # Saturday
            "2023-05-28",  # Sunday
            "2024-03-09",  # Saturday
            "2024-03-10",  # Sunday
        ]
        for w in weekends:
            assert MarketCalendar.is_trading_session(w) is False, f"Expected {w} to be recognized as non-trading weekend"

    def test_daylight_saving_transitions_regression(self):
        """
        Regression test for daylight-saving transitions:
        1. Spring 2023 forward transition (Sunday, March 12, 2023):
           - Friday 2023-03-10 is EST (UTC-5):
             - Open: 09:30 ET = 14:30:00 UTC
             - Close: 16:00 ET = 21:00:00 UTC
           - Monday 2023-03-13 is EDT (UTC-4):
             - Open: 09:30 ET = 13:30:00 UTC
             - Close: 16:00 ET = 20:00:00 UTC
        2. Fall 2023 back transition (Sunday, November 5, 2023):
           - Friday 2023-11-03 is EDT (UTC-4):
             - Open: 09:30 ET = 13:30:00 UTC
             - Close: 16:00 ET = 20:00:00 UTC
           - Monday 2023-11-06 is EST (UTC-5):
             - Open: 09:30 ET = 14:30:00 UTC
             - Close: 16:00 ET = 21:00:00 UTC
        """
        # 1. Spring Forward (March 2023)
        assert MarketCalendar.get_session_open_utc("2023-03-10") == pd.Timestamp("2023-03-10 14:30:00", tz="UTC")
        assert MarketCalendar.get_session_close_utc("2023-03-10") == pd.Timestamp("2023-03-10 21:00:00", tz="UTC")

        assert MarketCalendar.get_session_open_utc("2023-03-13") == pd.Timestamp("2023-03-13 13:30:00", tz="UTC")
        assert MarketCalendar.get_session_close_utc("2023-03-13") == pd.Timestamp("2023-03-13 20:00:00", tz="UTC")

        # 2. Fall Back (November 2023)
        assert MarketCalendar.get_session_open_utc("2023-11-03") == pd.Timestamp("2023-11-03 13:30:00", tz="UTC")
        assert MarketCalendar.get_session_close_utc("2023-11-03") == pd.Timestamp("2023-11-03 20:00:00", tz="UTC")

        assert MarketCalendar.get_session_open_utc("2023-11-06") == pd.Timestamp("2023-11-06 14:30:00", tz="UTC")
        assert MarketCalendar.get_session_close_utc("2023-11-06") == pd.Timestamp("2023-11-06 21:00:00", tz="UTC")


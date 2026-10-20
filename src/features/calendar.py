"""
US Equity Exchange Trading Calendar & Timezone Conversion.

Handles NYSE / NASDAQ trading session open and close times, official exchange
holidays, early-close sessions, and daylight saving time (EDT/EST) transitions
using the IANA America/New_York timezone.

HISTORICAL COVERAGE NOTICE:
- The holiday set (`US_MARKET_HOLIDAYS`) and early-close set (`US_MARKET_EARLY_CLOSES`)
  are statically verified for the 2018-2026 calendar years against official NYSE/NASDAQ schedules.
- For dates prior to 2018 (including the project's extended 1996-2017 historical universe),
  weekend filtering and daylight-saving time conversions remain mathematically valid via
  ZoneInfo("America/New_York"), but historical exchange holidays and ad-hoc closures (e.g.
  9/11 in 2001, Hurricane Sandy in 2012) are NOT statically registered in this table.
- Do NOT claim complete historical calendar coverage for pre-2018 data without integrating
  a comprehensive exchange calendar library (such as pandas_market_calendars or exchange_calendars).
"""

from datetime import datetime, time, timedelta
from typing import Set, Optional
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd

from src.data.market.validator import US_MARKET_HOLIDAYS

# Official US exchange timezone
EASTERN_TZ = ZoneInfo("America/New_York")

# Regular session hours in Eastern Time
REGULAR_MARKET_OPEN_TIME = time(9, 30)   # 09:30 ET
REGULAR_MARKET_CLOSE_TIME = time(16, 0)  # 16:00 ET
EARLY_MARKET_CLOSE_TIME = time(13, 0)    # 13:00 ET (1:00 PM ET)

# Official US equity exchange early close dates (13:00 ET close) 2018-2026 (verified)
# Typically: Black Friday (day after Thanksgiving), Christmas Eve (if weekday),
# and the day before Independence Day (July 3, if on a weekday).
US_MARKET_EARLY_CLOSES: Set[str] = {
    # 2018
    "2018-07-03", "2018-11-23", "2018-12-24",
    # 2019
    "2019-07-03", "2019-11-29", "2019-12-24",
    # 2020
    "2020-11-27", "2020-12-24",
    # 2021
    "2021-11-26",
    # 2022
    "2022-11-25",
    # 2023
    "2023-07-03", "2023-11-24",
    # 2024
    "2024-07-03", "2024-11-29", "2024-12-24",
    # 2025
    "2025-07-03", "2025-11-28", "2025-12-24",
    # 2026
    "2026-11-27", "2026-12-24",
}


class MarketCalendar:
    """
    Provides timezone-aware trading session hours and exchange calendar lookups.
    Verified for 2018-2026 exchange sessions.
    """

    @classmethod
    def is_trading_session(cls, date_str: str) -> bool:
        """Checks if a date is an active US trading day (Mon-Fri and non-holiday)."""
        dt = pd.to_datetime(date_str)
        # Saturday=5, Sunday=6
        if dt.weekday() >= 5:
            return False
        if date_str in US_MARKET_HOLIDAYS:
            return False
        return True

    @classmethod
    def is_early_close(cls, date_str: str) -> bool:
        """Returns True if the trading day closes early (13:00 ET)."""
        return date_str in US_MARKET_EARLY_CLOSES

    @classmethod
    def get_session_close_utc(cls, trading_date: str) -> pd.Timestamp:
        """
        Calculates the exact session close timestamp in UTC for a trading day.
        Respects:
        - Daylight Saving Time (EDT: 16:00 ET = 20:00:00 UTC).
        - Standard Time (EST: 16:00 ET = 21:00:00 UTC).
        - Early close sessions (13:00 ET = 17:00:00 UTC in EDT, 18:00:00 UTC in EST).
        """
        date_clean = str(trading_date).strip()[:10]
        close_time = EARLY_MARKET_CLOSE_TIME if cls.is_early_close(date_clean) else REGULAR_MARKET_CLOSE_TIME

        # Combine date and ET close time into a localized Eastern datetime
        dt_naive = datetime.strptime(date_clean, "%Y-%m-%d").replace(
            hour=close_time.hour,
            minute=close_time.minute,
            second=close_time.second,
        )
        dt_eastern = dt_naive.replace(tzinfo=EASTERN_TZ)
        dt_utc = dt_eastern.astimezone(ZoneInfo("UTC"))
        return pd.Timestamp(dt_utc)

    @classmethod
    def get_session_open_utc(cls, trading_date: str) -> pd.Timestamp:
        """
        Calculates the exact session open timestamp in UTC for a trading day.
        Respects:
        - Daylight Saving Time (EDT: 09:30 ET = 13:30:00 UTC).
        - Standard Time (EST: 09:30 ET = 14:30:00 UTC).
        """
        date_clean = str(trading_date).strip()[:10]
        open_time = REGULAR_MARKET_OPEN_TIME

        dt_naive = datetime.strptime(date_clean, "%Y-%m-%d").replace(
            hour=open_time.hour,
            minute=open_time.minute,
            second=open_time.second,
        )
        dt_eastern = dt_naive.replace(tzinfo=EASTERN_TZ)
        dt_utc = dt_eastern.astimezone(ZoneInfo("UTC"))
        return pd.Timestamp(dt_utc)

    @classmethod
    def get_next_trading_session(cls, trading_date: str) -> str:
        """
        Computes the next active trading session date string (YYYY-MM-DD),
        skipping weekends and official US equity exchange holidays.
        """
        curr = pd.Timestamp(trading_date) + np.timedelta64(1, "D")
        while True:
            date_str = curr.strftime("%Y-%m-%d")
            if cls.is_trading_session(date_str):
                return date_str
            curr += np.timedelta64(1, "D")

    @classmethod
    def get_next_session_open_utc(cls, trading_date: str) -> pd.Timestamp:
        """
        Computes the market open UTC timestamp of the NEXT active trading session.
        Guarantees:
        - Skips weekends (Friday -> Monday).
        - Skips holidays (Friday before Memorial Day -> Tuesday after Memorial Day).
        - Applies correct Eastern-to-UTC open time (13:30 UTC in EDT, 14:30 UTC in EST).
        """
        next_session = cls.get_next_trading_session(trading_date)
        return cls.get_session_open_utc(next_session)

    @classmethod
    def get_session_open_cutoff_utc(cls, trading_date: str, buffer_minutes: int = 15) -> pd.Timestamp:
        """
        Calculates the pre-open information and decision cutoff timestamp in UTC for a trading session.
        Applies a conservative pre-open buffer (default 15 minutes before 09:30 ET -> 09:15 ET).
        Respects:
        - Daylight Saving Time (EDT: 09:15 ET = 13:15:00 UTC).
        - Standard Time (EST: 09:15 ET = 14:15:00 UTC).
        Prevents news or SEC filings published at or immediately before market open from being
        assumed available to execute at the opening auction cross (09:30 ET).
        """
        open_utc = cls.get_session_open_utc(trading_date)
        return open_utc - timedelta(minutes=int(buffer_minutes))

    @classmethod
    def get_next_session_open_cutoff_utc(cls, trading_date: str, buffer_minutes: int = 15) -> pd.Timestamp:
        """
        Calculates the pre-open information and decision cutoff timestamp in UTC for the NEXT active trading session.
        Skips weekends and exchange holidays.
        """
        next_session = cls.get_next_trading_session(trading_date)
        return cls.get_session_open_cutoff_utc(next_session, buffer_minutes=buffer_minutes)

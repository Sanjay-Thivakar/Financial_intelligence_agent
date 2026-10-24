"""
Point-in-Time Availability and Temporal Alignment Engine for SEC Documents.

Provides rigorous, deterministic filtering of SEC financial facts and Form 8-K
events at exact market session decision cutoffs under strict anti-leakage invariants:
1. Decision Cutoff: 16:00:00 America/New_York converted to UTC.
2. Daylight Saving Awareness: Correctly handles EST (UTC-5) vs EDT (UTC-4).
3. Zero Lookahead: acceptance_timestamp <= decision_timestamp_utc.
4. After-hours Quarantining: Filings accepted after 16:00:00 NY enter only at session T+1.
5. Conservative Date-Only Fallback: If acceptance_timestamp lacks intraday time,
   filing_date < session_date is required.
6. Restatement & Amendment Isolation: Accession-level tracking ensures revisions
   filed later do not alter historical as-of views.
"""

from typing import Optional, Union, Dict, Any
from datetime import datetime, date, time
import zoneinfo
import numpy as np
import pandas as pd


NY_TZ = zoneinfo.ZoneInfo("America/New_York")
UTC_TZ = zoneinfo.ZoneInfo("UTC")


def get_market_close_utc(
    session_date: Union[str, date, datetime, pd.Timestamp],
    close_time_str: str = "16:00:00",
) -> pd.Timestamp:
    """
    Computes the exact UTC market close timestamp for a given trading session date.

    Correctly accounts for Daylight Saving Time in America/New_York:
    - Eastern Standard Time (EST): 16:00:00 NY = 21:00:00 UTC
    - Eastern Daylight Time (EDT): 16:00:00 NY = 20:00:00 UTC
    """
    if isinstance(session_date, str):
        session_dt = datetime.strptime(session_date[:10], "%Y-%m-%d")
    elif isinstance(session_date, (pd.Timestamp, datetime)):
        session_dt = session_date.date()
    elif isinstance(session_date, date):
        session_dt = session_date
    else:
        raise ValueError(f"Unsupported session_date type: {type(session_date)}")

    close_hour, close_min, close_sec = [int(x) for x in close_time_str.split(":")]
    local_close = datetime(
        session_dt.year,
        session_dt.month,
        session_dt.day,
        close_hour,
        close_min,
        close_sec,
        tzinfo=NY_TZ,
    )
    utc_close = local_close.astimezone(UTC_TZ)
    return pd.Timestamp(utc_close)


def get_pre_open_cutoff_utc(
    session_date: Union[str, date, datetime, pd.Timestamp],
    buffer_minutes: int = 15,
) -> pd.Timestamp:
    """
    Computes the pre-open decision cutoff timestamp in UTC (09:30 ET open minus buffer_minutes).
    Default 15m buffer -> 09:15:00 America/New_York.
    - EDT (UTC-4): 09:15:00 NY = 13:15:00 UTC
    - EST (UTC-5): 09:15:00 NY = 14:15:00 UTC
    """
    if isinstance(session_date, str):
        session_dt = datetime.strptime(session_date[:10], "%Y-%m-%d")
    elif isinstance(session_date, (pd.Timestamp, datetime)):
        session_dt = session_date.date()
    elif isinstance(session_date, date):
        session_dt = session_date
    else:
        raise ValueError(f"Unsupported session_date type: {type(session_date)}")

    open_dt = datetime(session_dt.year, session_dt.month, session_dt.day, 9, 30, 0, tzinfo=NY_TZ)
    cutoff_dt = open_dt - pd.Timedelta(minutes=buffer_minutes)
    return pd.Timestamp(cutoff_dt.astimezone(UTC_TZ))


def is_record_eligible_for_trade(
    acceptance_timestamp: Optional[Union[str, pd.Timestamp, datetime]],
    filing_date: Optional[Union[str, date]],
    session_date: Union[str, date, pd.Timestamp],
    decision_timing_mode: str = "MARKET_CLOSE",
    has_intraday_time: bool = True,
) -> bool:
    """
    Determines whether a document or fact is eligible to inform a trade decision under
    the specified timing convention:
    - MARKET_CLOSE: Decision at session T close (16:00 ET). Trade entry at session T+1 open (09:30 ET).
      Filing MUST have been accepted on or before session T close.
      Filings published after session T close (even before T+1 open) are strictly EXCLUDED from
      session T features because the decision was computed at session T close.
    - PRE_OPEN: Decision at session T+1 pre-open (09:15 ET). Trade entry at session T+1 open (09:30 ET).
      Filing must have been accepted on or before 09:15 ET.
    """
    if decision_timing_mode == "MARKET_CLOSE":
        return is_record_eligible_at_cutoff(
            acceptance_timestamp=acceptance_timestamp,
            filing_date=filing_date,
            session_date=session_date,
            close_time_str="16:00:00",
            has_intraday_time=has_intraday_time,
        )
    elif decision_timing_mode == "PRE_OPEN":
        cutoff_utc = get_pre_open_cutoff_utc(session_date)
        session_date_str = str(session_date)[:10]

        if acceptance_timestamp is not None and pd.notna(acceptance_timestamp) and has_intraday_time:
            acc_ts = pd.to_datetime(acceptance_timestamp, utc=True)
            if acc_ts.hour == 0 and acc_ts.minute == 0 and acc_ts.second == 0:
                if filing_date is not None and pd.notna(filing_date):
                    return str(filing_date)[:10] < session_date_str
                return False
            return acc_ts <= cutoff_utc

        if filing_date is not None and pd.notna(filing_date):
            return str(filing_date)[:10] < session_date_str

        return False
    else:
        raise ValueError(f"Unknown decision_timing_mode: {decision_timing_mode}")



def is_record_eligible_at_cutoff(
    acceptance_timestamp: Optional[Union[str, pd.Timestamp, datetime]],
    filing_date: Optional[Union[str, date]],
    session_date: Union[str, date, pd.Timestamp],
    close_time_str: str = "16:00:00",
    has_intraday_time: bool = True,
) -> bool:
    """
    Determines whether a document or fact is eligible to inform a prediction
    at trading session T close (16:00:00 America/New_York).

    Rules:
    - If acceptance_timestamp with intraday time is available:
      acceptance_timestamp <= session_close_utc.
    - If acceptance_timestamp is missing or has_intraday_time is False:
      Conservative fallback: filing_date < session_date (strictly before session date).
    - If neither timestamp nor filing_date is available:
      Excludes record (returns False).
    """
    session_close_utc = get_market_close_utc(session_date, close_time_str=close_time_str)
    session_date_str = str(session_date)[:10]

    # Case 1: Verified intraday acceptance timestamp
    if acceptance_timestamp is not None and pd.notna(acceptance_timestamp) and has_intraday_time:
        try:
            acc_ts = pd.to_datetime(acceptance_timestamp, utc=True)
            # If timestamp defaults to midnight 00:00:00 on filing_date, verify whether it's truly intraday
            if acc_ts.hour == 0 and acc_ts.minute == 0 and acc_ts.second == 0:
                # Date-only fallback
                if filing_date is not None and pd.notna(filing_date):
                    return str(filing_date)[:10] < session_date_str
                return False
            return acc_ts <= session_close_utc
        except Exception:
            pass

    # Case 2: Date-only fallback
    if filing_date is not None and pd.notna(filing_date):
        filing_date_str = str(filing_date)[:10]
        # Conservative requirement: filing must have occurred strictly before session date
        return filing_date_str < session_date_str

    return False


def filter_point_in_time_facts(
    df_facts: pd.DataFrame,
    as_of_timestamp: Union[str, pd.Timestamp, datetime],
    company_id: Optional[str] = None,
) -> pd.DataFrame:
    """
    Filters a financial facts DataFrame to include only facts known strictly
    on or before as_of_timestamp (in UTC).
    For each (company_id, concept, period_end), retains the latest accepted filing,
    preventing restatement lookahead leakage.
    """
    if df_facts.empty:
        return df_facts

    as_of_utc = pd.to_datetime(as_of_timestamp, utc=True)
    df = df_facts.copy()

    if not isinstance(df["acceptance_timestamp"].dtype, pd.DatetimeTZDtype):
        df["acceptance_timestamp"] = pd.to_datetime(df["acceptance_timestamp"], utc=True)

    # Filter by company if requested
    if company_id is not None:
        df = df[df["company_id"] == company_id]

    # Strict point-in-time boundary
    df_pit = df[df["acceptance_timestamp"] <= as_of_utc].copy()

    if df_pit.empty:
        return df_pit

    # Deduplicate restatements: sort by acceptance_timestamp ascending and take last observation
    df_pit = df_pit.sort_values(by=["period_end", "acceptance_timestamp"]).drop_duplicates(
        subset=["company_id", "concept", "period_end"],
        keep="last",
    )
    return df_pit


def filter_point_in_time_events(
    df_events: pd.DataFrame,
    as_of_timestamp: Union[str, pd.Timestamp, datetime],
    company_id: Optional[str] = None,
) -> pd.DataFrame:
    """
    Filters a Form 8-K events DataFrame to include only events public on or before
    as_of_timestamp (in UTC).
    """
    if df_events.empty:
        return df_events

    as_of_utc = pd.to_datetime(as_of_timestamp, utc=True)
    df = df_events.copy()

    if not isinstance(df["acceptance_timestamp"].dtype, pd.DatetimeTZDtype):
        df["acceptance_timestamp"] = pd.to_datetime(df["acceptance_timestamp"], utc=True)

    if company_id is not None:
        df = df[df["company_id"] == company_id]

    return df[df["acceptance_timestamp"] <= as_of_utc].copy()

"""
SEC Corporate Event Feature Engineering Engine (Phase 5F).

Extracts point-in-time, factual statistical features from SEC Form 8-K corporate event metadata:
1. sec_event_count_5d: Deduplicated count of eligible 8-Ks in preceding 5-trading-session window.
2. sec_earnings_release_in_window: Binary indicator (0/1) for eligible Item 2.02 earnings releases in window.
3. sec_days_since_last_8k: Age in calendar days of the most recent eligible 8-K as of decision cutoff.

Point-in-Time Availability & Leakage Controls:
- Conservative 5-minute public dissemination buffer (Phase 5E.1).
- Filing is eligible at T_decision iff: T_acceptance + 5 minutes <= T_decision.
- For 09:15 ET pre-open cutoff, any filing accepted at or after 09:10 ET is excluded.
- Filings with missing or unparseable acceptance timestamps are excluded from time-sensitive features.
- Missingness semantics:
  - 0: Company event coverage is active/checked, but no qualifying event occurred in the window.
  - NaN: Source or event coverage is unavailable/unverified (never convert missing source to zero).
"""

from datetime import timedelta
import logging
from typing import Dict, List, Optional, Any, Set, Tuple
import numpy as np
import pandas as pd

from src.features.calendar import MarketCalendar, EASTERN_TZ
from src.features.config import SECEventFeatureConfig

logger = logging.getLogger(__name__)


class SECEventFeatureEngine:
    """Computes point-in-time factual statistical features from SEC Form 8-K corporate filings."""

    def __init__(
        self,
        df_events: Optional[pd.DataFrame] = None,
        config: Optional[SECEventFeatureConfig] = None,
        covered_company_ids: Optional[Set[str]] = None,
    ):
        """
        :param df_events: Processed Form 8-K events DataFrame.
        :param config: Configuration specifying dissemination buffer, window, and items.
        :param covered_company_ids: Explicit set of company_ids with verified event source coverage.
                                    If None, inferred from unique company_ids in df_events.
        """
        self.config = config or SECEventFeatureConfig()
        self._company_events: Dict[str, pd.DataFrame] = {}
        self.covered_company_ids: Set[str] = set(covered_company_ids) if covered_company_ids else set()

        if df_events is not None and not df_events.empty:
            self._index_events(df_events)

    def _index_events(self, df_events: pd.DataFrame) -> None:
        """Indexes and sorts events by company_id for accelerated point-in-time lookups."""
        valid_df = df_events[df_events["company_id"].notna()].copy()
        if valid_df.empty:
            return

        # Ensure acceptance_timestamp is timezone-aware UTC datetime
        if "acceptance_timestamp" in valid_df.columns:
            valid_df["acceptance_timestamp"] = pd.to_datetime(valid_df["acceptance_timestamp"], utc=True)

        for cid, grp in valid_df.groupby("company_id"):
            cid_str = str(cid)
            self.covered_company_ids.add(cid_str)
            # Sort chronologically by acceptance_timestamp
            self._company_events[cid_str] = grp.sort_values(by="acceptance_timestamp").reset_index(drop=True)

    def is_filing_eligible(
        self,
        acceptance_timestamp: Any,
        decision_timestamp: Any,
        buffer_minutes: Optional[int] = None,
    ) -> bool:
        """
        Determines whether an SEC filing is eligible at a specific decision cutoff under the
        conservative dissemination buffer rule:
            T_acceptance + buffer <= T_decision
        Equivalently:
            T_acceptance <= T_decision - buffer

        For a 09:15 ET cutoff and 5-minute buffer:
        - Filing accepted at 09:09:59 ET -> eligible (09:09:59 + 5m = 09:14:59 <= 09:15:00)
        - Filing accepted at 09:10:00 ET -> excluded (09:10:00 + 5m = 09:15:00, boundary rule: at or after 09:10 excluded)
        - Filing accepted at 09:10:01 ET -> excluded
        """
        if pd.isna(acceptance_timestamp) or acceptance_timestamp is None:
            return False

        buf_min = buffer_minutes if buffer_minutes is not None else self.config.dissemination_buffer_minutes
        buffer_td = timedelta(minutes=buf_min)

        try:
            acc_ts = pd.to_datetime(acceptance_timestamp, utc=True)
            dec_ts = pd.to_datetime(decision_timestamp, utc=True)
        except Exception:
            return False

        # Strictly enforce: acceptance time + buffer must be strictly less than or equal to decision time
        # Boundary rule: a filing accepted at or after (T_decision - buffer) is excluded
        cutoff_boundary = dec_ts - buffer_td
        return acc_ts < cutoff_boundary

    def get_as_of_snapshot(
        self,
        company_id: str,
        decision_timestamp: Any,
        trading_date: Optional[str] = None,
        lookback_sessions: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Computes factual SEC corporate event features for a company at an exact decision cutoff.
        """
        cid_str = str(company_id)
        dec_utc = pd.to_datetime(decision_timestamp, utc=True)
        sessions_w = lookback_sessions or self.config.window_sessions

        snapshot: Dict[str, Any] = {
            "company_id": cid_str,
            "decision_timestamp": dec_utc,
            "sec_event_available": False,
            "sec_event_coverage_status": "source_unavailable",
            "sec_event_count_5d": np.nan,
            "sec_earnings_release_in_window": np.nan,
            "sec_days_since_last_8k": np.nan,
        }

        # Check coverage: if company is not in covered set, preserve NaN
        if cid_str not in self.covered_company_ids:
            return snapshot

        snapshot["sec_event_coverage_status"] = "active"
        snapshot["sec_event_available"] = True

        comp_df = self._company_events.get(cid_str)
        if comp_df is None or comp_df.empty:
            # Source checked, verified zero filings in history
            snapshot["sec_event_count_5d"] = 0
            snapshot["sec_earnings_release_in_window"] = 0
            return snapshot

        # Filter strictly to eligible filings as of cutoff
        buf_min = self.config.dissemination_buffer_minutes
        eligible_mask = [
            self.is_filing_eligible(row["acceptance_timestamp"], dec_utc, buffer_minutes=buf_min)
            for _, row in comp_df.iterrows()
        ]
        eligible_filings = comp_df[eligible_mask]

        if eligible_filings.empty:
            # Verified active coverage, zero eligible events prior to decision cutoff
            snapshot["sec_event_count_5d"] = 0
            snapshot["sec_earnings_release_in_window"] = 0
            return snapshot

        # Most recent eligible filing
        latest_row = eligible_filings.iloc[-1]
        latest_acc_ts = pd.to_datetime(latest_row["acceptance_timestamp"], utc=True)
        # Calendar-day age (unit explicitly documented: floating-point days)
        age_days = (dec_utc - latest_acc_ts).total_seconds() / 86400.0
        snapshot["sec_days_since_last_8k"] = float(age_days)

        # Compute preceding 5-session window boundary
        # If trading_date is provided, use MarketCalendar to find the start of the 5-session window
        if trading_date:
            date_clean = str(trading_date)[:10]
            # Window encompasses the 5 trading sessions ending on trading_date
            # Preceding 5 sessions: find session 5 sessions prior
            # Start cutoff is the decision cutoff for session (T - 5)
            prior_date = date_clean
            for _ in range(sessions_w):
                # Step backwards across calendar
                dt = pd.Timestamp(prior_date) - timedelta(days=1)
                while not MarketCalendar.is_trading_session(dt.strftime("%Y-%m-%d")):
                    dt -= timedelta(days=1)
                prior_date = dt.strftime("%Y-%m-%d")

            # Cutoff timestamp for the session immediately prior to the 5-session window
            window_start_utc = MarketCalendar.get_session_open_cutoff_utc(prior_date, buffer_minutes=15)
        else:
            # Fallback: 7 calendar days (~5 trading days)
            window_start_utc = dec_utc - timedelta(days=7)

        # Filter filings strictly within [window_start_utc, dec_utc]
        # Any filing in window must satisfy:
        # T_acceptance + buffer <= dec_utc (already enforced by eligible_filings)
        # AND T_acceptance + buffer > window_start_utc
        buf_td = timedelta(minutes=buf_min)
        window_mask = (eligible_filings["acceptance_timestamp"] + buf_td) > window_start_utc
        window_filings = eligible_filings[window_mask]

        event_count = len(window_filings)
        snapshot["sec_event_count_5d"] = int(event_count)

        # Check for Item 2.02 earnings releases in window
        has_earnings = False
        earnings_code = self.config.earnings_item
        for _, row in window_filings.iterrows():
            item_list = row.get("item_list")
            if isinstance(item_list, (list, tuple)) and earnings_code in item_list:
                has_earnings = True
                break
            raw_items = str(row.get("items", ""))
            if earnings_code in raw_items:
                has_earnings = True
                break

        snapshot["sec_earnings_release_in_window"] = 1 if has_earnings else 0
        return snapshot

    def compute_snapshots_for_decisions(self, df_decisions: pd.DataFrame) -> pd.DataFrame:
        """
        Batch extracts event snapshots for an aligned DataFrame containing
        'company_id', 'decision_timestamp', and optionally 'trading_date'.
        """
        rows = []
        has_date = "trading_date" in df_decisions.columns

        for _, dec_row in df_decisions.iterrows():
            cid = dec_row["company_id"]
            dec_ts = dec_row["decision_timestamp"]
            tr_date = dec_row["trading_date"] if has_date else None
            snap = self.get_as_of_snapshot(cid, dec_ts, trading_date=tr_date)
            rows.append(snap)

        return pd.DataFrame(rows)

"""
Baseline Financial News Feature Engineering Engine.

Extracts point-in-time, deterministic, volume, recency, and source-quality features
from canonical financial news records at exact trading-session decision cutoffs.
Guarantees zero look-ahead bias, rejects same-day date-only ambiguity, and strictly
avoids unverified sentiment invention.
"""

import logging
from typing import Dict, List, Optional, Any
import numpy as np
import pandas as pd

from src.features.config import NewsFeatureConfig

logger = logging.getLogger(__name__)


class NewsFeatureEngine:
    """
    Computes deterministic baseline features from point-in-time financial news records.
    Guarantees:
    1. Zero look-ahead leakage: articles published after decision_timestamp are strictly excluded.
    2. Date-only safety: articles lacking intraday time cannot leak into same-day decisions.
    3. Trailing window boundaries: [decision_timestamp - lookback, decision_timestamp].
    4. Deterministic non-predictive baseline metrics (article counts, source diversity, body availability, recency).
    5. No unverified sentiment scores or return predictions.
    """

    def __init__(
        self,
        df_news: Optional[pd.DataFrame] = None,
        config: Optional[NewsFeatureConfig] = None,
    ):
        self.config = config or NewsFeatureConfig()
        self._company_news: Dict[str, pd.DataFrame] = {}

        if df_news is not None and not df_news.empty:
            self._index_news(df_news)

    def _index_news(self, df_news: pd.DataFrame) -> None:
        """Indexes news records by company_id for rapid point-in-time lookups."""
        # Work only with records that have a resolved company_id
        valid_news = df_news[df_news["company_id"].notna()].copy()
        if valid_news.empty:
            return

        # Ensure published_at is timezone-aware UTC datetime
        if not isinstance(valid_news["published_at"].dtype, pd.DatetimeTZDtype):
            valid_news["published_at"] = pd.to_datetime(valid_news["published_at"], utc=True)

        for company_id, group in valid_news.groupby("company_id"):
            self._company_news[str(company_id)] = group.sort_values(by="published_at").reset_index(drop=True)

    def is_article_eligible(
        self,
        article_pub_at: Any,
        has_intraday_time: bool,
        article_pub_date: str,
        decision_timestamp: Any,
    ) -> bool:
        """
        Determines whether a news article is defensibly available at a decision cutoff.
        - Strict cutoff: published_at <= decision_timestamp.
        - Date-only handling: if has_intraday_time is False, the exact time of release during
          that date is unknown. To prevent same-day lookahead leakage, date-only articles
          are eligible only on subsequent dates (published_date < decision_date).
        """
        if pd.isna(article_pub_at):
            return False

        try:
            pub_ts = pd.to_datetime(article_pub_at, utc=True)
            dec_ts = pd.to_datetime(decision_timestamp, utc=True)
        except Exception:
            return False

        if pub_ts > dec_ts:
            return False

        if not has_intraday_time:
            if self.config.require_intraday_time:
                return False
            if not self.config.allow_date_only:
                return False
            # Check date-level lookahead: cannot use date-only article on the same day as decision
            decision_date_str = dec_ts.strftime("%Y-%m-%d")
            if str(article_pub_date) >= decision_date_str:
                return False

        return True

    def get_as_of_snapshot(
        self,
        company_id: str,
        decision_timestamp: pd.Timestamp,
    ) -> Dict[str, Any]:
        """
        Extracts baseline news features for a company as of an exact decision cutoff.
        """
        if decision_timestamp.tzinfo is None:
            dec_utc = decision_timestamp.tz_localize("UTC")
        else:
            dec_utc = decision_timestamp.tz_convert("UTC")

        snapshot: Dict[str, Any] = {
            "company_id": company_id,
            "as_of_timestamp": dec_utc,
            "news_available": False,
        }

        # Initialize default NaN / zero values for all configured windows
        for w in self.config.trailing_windows:
            snapshot[f"news_count_{w}d"] = 0
            snapshot[f"news_unique_sources_{w}d"] = 0
            snapshot[f"news_has_body_ratio_{w}d"] = np.nan
            snapshot[f"news_has_intraday_ratio_{w}d"] = np.nan

        snapshot["news_recency_hours"] = np.nan
        snapshot["news_article_count_missing"] = True
        snapshot["news_missing"] = True

        comp_articles = self._company_news.get(company_id)
        if comp_articles is None or comp_articles.empty:
            return snapshot

        # Filter strictly to eligible articles at or before decision cutoff
        eligible_mask = [
            self.is_article_eligible(
                article_pub_at=row["published_at"],
                has_intraday_time=bool(row.get("has_intraday_time", True)),
                article_pub_date=str(row.get("published_date", "")),
                decision_timestamp=dec_utc,
            )
            for _, row in comp_articles.iterrows()
        ]
        eligible_articles = comp_articles[eligible_mask]

        if eligible_articles.empty:
            return snapshot

        snapshot["news_article_count_missing"] = False

        # Calculate trailing window features
        for w in self.config.trailing_windows:
            start_window = dec_utc - np.timedelta64(int(w), "D")
            window_df = eligible_articles[
                (eligible_articles["published_at"] >= start_window) &
                (eligible_articles["published_at"] <= dec_utc)
            ]
            count = len(window_df)
            snapshot[f"news_count_{w}d"] = count

            if count > 0:
                snapshot[f"news_unique_sources_{w}d"] = int(window_df["source"].nunique())
                if "has_body_text" in window_df.columns:
                    snapshot[f"news_has_body_ratio_{w}d"] = float(window_df["has_body_text"].mean())
                else:
                    body_present = (window_df["article_text"].fillna("").str.strip() != "")
                    snapshot[f"news_has_body_ratio_{w}d"] = float(body_present.mean())

                snapshot[f"news_has_intraday_ratio_{w}d"] = float(window_df["has_intraday_time"].mean())
            else:
                snapshot[f"news_unique_sources_{w}d"] = 0
                snapshot[f"news_has_body_ratio_{w}d"] = np.nan
                snapshot[f"news_has_intraday_ratio_{w}d"] = np.nan

        # Calculate recency in hours to the most recent eligible article within horizon
        max_lookback_start = dec_utc - np.timedelta64(int(self.config.recency_max_days), "D")
        recent_candidates = eligible_articles[
            (eligible_articles["published_at"] >= max_lookback_start) &
            (eligible_articles["published_at"] <= dec_utc)
        ]
        if not recent_candidates.empty:
            latest_pub = recent_candidates["published_at"].max()
            diff_hours = (dec_utc - latest_pub).total_seconds() / 3600.0
            snapshot["news_recency_hours"] = round(float(diff_hours), 2)
            snapshot["news_available"] = True
            snapshot["news_missing"] = False
        else:
            snapshot["news_recency_hours"] = np.nan
            snapshot["news_available"] = False
            snapshot["news_missing"] = True

        return snapshot

    def compute_snapshots_for_decisions(self, decisions_df: pd.DataFrame) -> pd.DataFrame:
        """
        Computes news snapshots for an aligned series of (company_id, decision_timestamp) pairs.
        Preserves the index of decisions_df for deterministic horizontal alignment.
        """
        if decisions_df.empty:
            return pd.DataFrame()

        rows = []
        for _, dec_row in decisions_df.iterrows():
            cid = str(dec_row["company_id"])
            dec_ts = pd.to_datetime(dec_row["decision_timestamp"], utc=True)
            snapshot = self.get_as_of_snapshot(cid, dec_ts)
            rows.append(snapshot)

        return pd.DataFrame(rows, index=decisions_df.index)

"""
Temporal Alignment and Point-in-Time Feature Harmonization Module.

Harmonizes market-derived technical indicators with SEC EDGAR fundamental
snapshots at exact trading-session decision cutoffs. Enforces point-in-time
integrity, rejects look-ahead leakage, preserves provenance metadata, and
verifies universe membership intervals.
"""

import logging
from typing import Dict, List, Any, Optional
import numpy as np
import pandas as pd

from src.features.market import MarketFeatureEngine
from src.features.fundamental import FundamentalFeatureEngine
from src.features.news import NewsFeatureEngine
from src.features.event import SECEventFeatureEngine

logger = logging.getLogger(__name__)


class LookaheadLeakageError(Exception):
    """Raised when an input observation has a timestamp strictly in the future of the decision cutoff."""
    pass


class TemporalAligner:
    """Joins market, fundamental, news, and SEC event features at exact point-in-time decision timestamps."""

    def __init__(
        self,
        market_engine: Optional[MarketFeatureEngine] = None,
        fundamental_engine: Optional[FundamentalFeatureEngine] = None,
        news_engine: Optional[NewsFeatureEngine] = None,
        event_engine: Optional[SECEventFeatureEngine] = None,
        universe_df: Optional[pd.DataFrame] = None,
    ):
        self.market_engine = market_engine or MarketFeatureEngine()
        self.fundamental_engine = fundamental_engine
        self.news_engine = news_engine
        self.event_engine = event_engine
        self.universe_df = universe_df
        self._universe_index: Dict[str, List[Dict[str, Any]]] = {}
        if universe_df is not None and not universe_df.empty:
            self._build_universe_index(universe_df)

    def _build_universe_index(self, universe_df: pd.DataFrame) -> None:
        """Indexes universe intervals by company_id for rapid membership queries."""
        for _, row in universe_df.iterrows():
            cid = str(row["company_id"])
            eff_from = str(row.get("effective_from", "1900-01-01"))
            eff_to = row.get("effective_to")
            eff_to_str = str(eff_to) if pd.notna(eff_to) and eff_to else "9999-12-31"

            if cid not in self._universe_index:
                self._universe_index[cid] = []
            self._universe_index[cid].append({
                "ticker": row.get("ticker"),
                "company_name": row.get("company_name"),
                "effective_from": eff_from,
                "effective_to": eff_to_str,
            })

    def is_sp500_active_on_date(self, company_id: str, trading_date: str) -> bool:
        """Checks if a company was an active constituent of S&P 500 on a given date."""
        intervals = self._universe_index.get(company_id)
        if not intervals:
            # If universe not indexed or company not found, default to True (unconstrained)
            return True

        for interval in intervals:
            if interval["effective_from"] <= trading_date < interval["effective_to"]:
                return True
        return False

    def align_features(
        self,
        df_market: pd.DataFrame,
        strict_leakage_check: bool = True,
        filter_sp500_active: bool = False,
    ) -> pd.DataFrame:
        """
        Computes market features, extracts corresponding fundamental snapshots,
        and joins them into a unified, point-in-time aligned feature matrix.

        :param df_market: Raw normalized market observations.
        :param strict_leakage_check: If True, raises LookaheadLeakageError if any
                                     observation timestamp > decision_timestamp.
        :param filter_sp500_active: If True, filters rows to only sessions where the
                                    company was an active S&P 500 constituent.
        :return: Fully aligned, point-in-time feature DataFrame.
        """
        if df_market.empty:
            return pd.DataFrame()

        # 1. Compute market features (includes attached decision_timestamp)
        df_mkt_feat = self.market_engine.compute_features(df_market)

        # 2. Check market look-ahead constraints
        if strict_leakage_check:
            self._verify_market_timing(df_mkt_feat)

        # 3. Optional S&P 500 membership interval filtering / annotation
        if self._universe_index:
            active_flags = [
                self.is_sp500_active_on_date(row["company_id"], row["trading_date"])
                for _, row in df_mkt_feat.iterrows()
            ]
            df_mkt_feat["is_sp500_constituent"] = active_flags
            if filter_sp500_active:
                df_mkt_feat = df_mkt_feat[df_mkt_feat["is_sp500_constituent"]].reset_index(drop=True)
                if df_mkt_feat.empty:
                    return pd.DataFrame()
        else:
            df_mkt_feat["is_sp500_constituent"] = True

        # 4. If fundamental engine is provided, extract and join fundamental snapshots
        if self.fundamental_engine is not None:
            fund_snapshots = self.fundamental_engine.compute_snapshots_for_decisions(
                df_mkt_feat[["company_id", "decision_timestamp"]]
            )

            # Drop redundant join keys from fund_snapshots before horizontal concatenation
            drop_cols = ["company_id", "as_of_timestamp"]
            fund_cols_to_add = fund_snapshots.drop(columns=[c for c in drop_cols if c in fund_snapshots.columns])

            aligned_df = pd.concat([df_mkt_feat, fund_cols_to_add], axis=1)

            # 5. Check fundamental look-ahead constraints
            if strict_leakage_check:
                self._verify_fundamental_timing(aligned_df)
        else:
            aligned_df = df_mkt_feat

        # 6. If news engine is provided, extract and join news baseline features
        if self.news_engine is not None:
            news_snapshots = self.news_engine.compute_snapshots_for_decisions(
                df_mkt_feat[["company_id", "decision_timestamp"]]
            )
            drop_cols = ["company_id", "as_of_timestamp"]
            news_cols_to_add = news_snapshots.drop(columns=[c for c in drop_cols if c in news_snapshots.columns])
            aligned_df = pd.concat([aligned_df, news_cols_to_add], axis=1)

        # 7. If event engine is provided, extract and join SEC corporate event features
        if self.event_engine is not None:
            event_snapshots = self.event_engine.compute_snapshots_for_decisions(
                df_mkt_feat[["company_id", "decision_timestamp", "trading_date"]]
            )
            drop_cols = ["company_id", "decision_timestamp"]
            event_cols_to_add = event_snapshots.drop(columns=[c for c in drop_cols if c in event_snapshots.columns])
            aligned_df = pd.concat([aligned_df, event_cols_to_add], axis=1)

        # 8. Overall metadata & missingness indicators
        aligned_df["alignment_provenance"] = "temporal_as_of_aligner_v1"
        aligned_df = self._add_completeness_flags(aligned_df)

        return aligned_df

    def _verify_market_timing(self, df: pd.DataFrame) -> None:
        """Verifies that market timestamp does not exceed decision_timestamp."""
        mkt_ts = pd.to_datetime(df["timestamp"], utc=True)
        dec_ts = pd.to_datetime(df["decision_timestamp"], utc=True)
        violations = mkt_ts > dec_ts
        if violations.any():
            count = violations.sum()
            raise LookaheadLeakageError(
                f"FATAL LOOK-AHEAD ERROR: {count} market observations have "
                f"timestamp > decision_timestamp!"
            )

    def _verify_fundamental_timing(self, df: pd.DataFrame) -> None:
        """Verifies that no fundamental fact was accepted after the decision cutoff."""
        dec_ts = pd.to_datetime(df["decision_timestamp"], utc=True)
        ts_cols = [c for c in df.columns if c.startswith("fundamental_") and c.endswith("_acceptance_timestamp")]

        for col in ts_cols:
            fact_ts = pd.to_datetime(df[col], utc=True)
            # Only check non-null timestamps
            valid_mask = fact_ts.notna()
            violations = valid_mask & (fact_ts > dec_ts)
            if violations.any():
                count = violations.sum()
                bad_row = df[violations].iloc[0]
                raise LookaheadLeakageError(
                    f"FATAL LOOK-AHEAD ERROR in {col}: {count} fundamental records have "
                    f"acceptance timestamp ({bad_row[col]}) > decision timestamp ({bad_row['decision_timestamp']})!"
                )

    def _add_completeness_flags(self, df: pd.DataFrame) -> pd.DataFrame:
        """Adds aggregate missingness flags for downstream modeling."""
        mkt_missing_cols = [c for c in df.columns if c.startswith("market_") and c.endswith("_missing")]
        if mkt_missing_cols:
            df["market_features_has_missing"] = df[mkt_missing_cols].any(axis=1)
        else:
            df["market_features_has_missing"] = False

        fund_missing_cols = [c for c in df.columns if c.startswith("fundamental_") and c.endswith("_missing")]
        if fund_missing_cols:
            df["fundamental_features_has_missing"] = df[fund_missing_cols].any(axis=1)
        else:
            df["fundamental_features_has_missing"] = True

        news_missing_cols = [c for c in df.columns if c.startswith("news_") and c.endswith("_missing")]
        if news_missing_cols:
            df["news_features_has_missing"] = df[news_missing_cols].any(axis=1)
        else:
            df["news_features_has_missing"] = True

        return df

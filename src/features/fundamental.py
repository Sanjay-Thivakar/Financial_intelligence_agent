"""
Fundamental Feature Engineering Module.

Extracts point-in-time fundamental accounting features and financial ratios
from normalized SEC EDGAR XBRL facts. Guarantees zero look-ahead bias,
preserves accession provenance, tracks restatements immutably, and avoids
treating missing financial values as zero.
"""

import logging
from typing import Dict, List, Any, Optional
import numpy as np
import pandas as pd

from src.features.config import FundamentalFeatureConfig, DEFAULT_CONCEPT_MAPPINGS

logger = logging.getLogger(__name__)


class FundamentalFeatureEngine:
    """Extracts point-in-time fundamental statement features and financial health ratios."""

    def __init__(
        self,
        df_facts: pd.DataFrame,
        config: Optional[FundamentalFeatureConfig] = None,
    ):
        """
        Initializes the fundamental feature engine with processed SEC facts.
        :param df_facts: Processed SEC facts DataFrame conforming to PROCESSED_SEC_FACT_SCHEMA.
        :param config: Configuration specifying concept mappings and ratio computation.
        """
        self.config = config or FundamentalFeatureConfig()
        self.df_facts = df_facts.copy() if not df_facts.empty else pd.DataFrame()

        # Pre-process facts for efficient point-in-time querying
        if not self.df_facts.empty:
            if "acceptance_timestamp" in self.df_facts.columns:
                self.df_facts["acceptance_timestamp"] = pd.to_datetime(
                    self.df_facts["acceptance_timestamp"], utc=True
                )
            # Index/group by company_id for accelerated queries
            self._company_facts: Dict[str, pd.DataFrame] = {
                cid: grp for cid, grp in self.df_facts.groupby("company_id")
            }
        else:
            self._company_facts = {}

    def get_as_of_snapshot(
        self,
        company_id: str,
        as_of_timestamp: pd.Timestamp,
    ) -> Dict[str, Any]:
        """
        Extracts the authoritative fundamental snapshot for a company as of an exact decision timestamp.
        Guarantees:
        1. Only filings with acceptance_timestamp <= as_of_timestamp are considered.
        2. Restatement-safe: if a 10-K/A was accepted AFTER as_of_timestamp, it is ignored;
           if accepted BEFORE, it supersedes the original 10-K for that period.
        3. Missing accounting concepts are preserved as NaN (never imputed as 0.0).
        4. Every returned concept includes source accession number, period end, and acceptance timestamp.
        """
        if as_of_timestamp.tzinfo is None:
            as_of_utc = as_of_timestamp.tz_localize("UTC")
        else:
            as_of_utc = as_of_timestamp.tz_convert("UTC")

        snapshot: Dict[str, Any] = {
            "company_id": company_id,
            "as_of_timestamp": as_of_utc,
            "fundamental_available": False,
        }

        # Check if we have any facts for this company
        comp_facts = self._company_facts.get(company_id)
        if comp_facts is None or comp_facts.empty:
            return self._build_empty_snapshot(snapshot)

        # 1. Filter strictly to publicly available facts as of cutoff
        available_facts = comp_facts[comp_facts["acceptance_timestamp"] <= as_of_utc]
        if available_facts.empty:
            return self._build_empty_snapshot(snapshot)

        snapshot["fundamental_available"] = True

        # 2. Extract latest valid observation for each target accounting concept
        extracted_values: Dict[str, float] = {}
        has_stale_facts = False
        all_facts_stale = True

        for canonical_name, concept_tags in self.config.concept_mappings.items():
            fact_match = self._extract_latest_concept_fact(
                available_facts=available_facts,
                concept_tags=concept_tags,
                as_of_utc=as_of_utc,
            )

            val_col = f"fundamental_{canonical_name}"
            missing_col = f"{val_col}_missing"
            accn_col = f"{val_col}_accn"
            period_col = f"{val_col}_period_end"
            form_col = f"{val_col}_form"
            accept_ts_col = f"{val_col}_acceptance_timestamp"
            age_col = f"{val_col}_age_days"
            stale_col = f"{val_col}_is_stale"

            if fact_match is not None:
                val = float(fact_match["value"])
                snapshot[val_col] = val
                snapshot[missing_col] = False
                snapshot[accn_col] = fact_match["accession_number"]
                snapshot[period_col] = fact_match["period_end"]
                snapshot[form_col] = fact_match["form"]
                accept_ts = fact_match["acceptance_timestamp"]
                snapshot[accept_ts_col] = accept_ts
                extracted_values[canonical_name] = val

                # Staleness check against configured max_staleness_days
                accept_dt = pd.to_datetime(accept_ts, utc=True)
                age_days = (as_of_utc - accept_dt).total_seconds() / 86400.0
                is_stale = age_days > self.config.max_staleness_days
                snapshot[age_col] = round(age_days, 1)
                snapshot[stale_col] = is_stale
                if is_stale:
                    has_stale_facts = True
                else:
                    all_facts_stale = False
            else:
                snapshot[val_col] = np.nan
                snapshot[missing_col] = True
                snapshot[accn_col] = None
                snapshot[period_col] = None
                snapshot[form_col] = None
                snapshot[accept_ts_col] = None
                snapshot[age_col] = np.nan
                snapshot[stale_col] = False

        snapshot["fundamental_has_stale_facts"] = has_stale_facts
        snapshot["fundamental_all_facts_stale"] = all_facts_stale if extracted_values else False

        # 3. Compute derived financial ratios strictly when components are present
        if self.config.compute_ratios:
            snapshot = self._compute_ratios(snapshot, extracted_values)

        return snapshot

    def _extract_latest_concept_fact(
        self,
        available_facts: pd.DataFrame,
        concept_tags: List[str],
        as_of_utc: pd.Timestamp,
    ) -> Optional[Dict[str, Any]]:
        """
        Extracts the most recent period fact among prioritized concept tags.
        Guarantees:
        1. Evaluates all concept tags collectively to find the true latest available period_end.
        2. If multiple concept tags report the same latest period_end, breaks ties using
           the priority order in concept_tags.
        3. If multiple filings exist for the latest period_end (e.g. 10-K and 10-K/A amendment),
           picks the latest filing publicly available as of as_of_utc.
        4. Breaks any timestamp ties deterministically using accession_number.
        """
        candidates = available_facts[available_facts["concept"].isin(concept_tags)]
        if candidates.empty:
            return None

        # 1. Find the latest available fiscal period_end date across all candidate tags
        max_period_end = candidates["period_end"].max()
        period_matches = candidates[candidates["period_end"] == max_period_end].copy()

        # 2. Prioritize by concept tag priority order (first in concept_tags has priority 0)
        tag_priority = {t: i for i, t in enumerate(concept_tags)}
        period_matches["_priority"] = period_matches["concept"].map(tag_priority).fillna(999)
        min_priority = period_matches["_priority"].min()
        best_tag_matches = period_matches[period_matches["_priority"] == min_priority]

        # 3. Sort deterministically by acceptance_timestamp and accession_number
        sorted_matches = best_tag_matches.sort_values(
            by=["acceptance_timestamp", "accession_number"],
            ascending=[True, True]
        )
        latest_fact = sorted_matches.iloc[-1].to_dict()
        latest_fact.pop("_priority", None)
        return latest_fact

    def _compute_ratios(
        self,
        snapshot: Dict[str, Any],
        values: Dict[str, float],
    ) -> Dict[str, Any]:
        """
        Computes financial health and valuation ratios.
        Never invents ratios when required components are missing or zero.
        """
        # Helper safe division
        def safe_div(num_key: str, den_key: str, ratio_name: str) -> None:
            num = values.get(num_key)
            den = values.get(den_key)
            r_col = f"fundamental_ratio_{ratio_name}"
            m_col = f"{r_col}_missing"

            if num is not None and den is not None and not np.isnan(num) and not np.isnan(den) and den > 0:
                snapshot[r_col] = float(num / den)
                snapshot[m_col] = False
            else:
                snapshot[r_col] = np.nan
                snapshot[m_col] = True

        # Debt-to-Assets: total_liabilities / total_assets
        safe_div("total_liabilities", "total_assets", "debt_to_assets")

        # Debt-to-Equity: total_liabilities / stockholders_equity
        safe_div("total_liabilities", "stockholders_equity", "debt_to_equity")

        # Net Profit Margin: net_income / revenue
        safe_div("net_income", "revenue", "net_margin")

        # Return on Assets (ROA): net_income / total_assets
        safe_div("net_income", "total_assets", "roa")

        # Current Ratio: current_assets / current_liabilities
        safe_div("current_assets", "current_liabilities", "current_ratio")

        # Operating Cash Flow to Net Income: operating_cash_flow / net_income
        safe_div("operating_cash_flow", "net_income", "ocf_to_net_income")

        return snapshot

    def _build_empty_snapshot(self, base_snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """Fills snapshot with NaN and True missing indicators when no facts exist."""
        for canonical_name in self.config.concept_mappings:
            val_col = f"fundamental_{canonical_name}"
            base_snapshot[val_col] = np.nan
            base_snapshot[f"{val_col}_missing"] = True
            base_snapshot[f"{val_col}_accn"] = None
            base_snapshot[f"{val_col}_period_end"] = None
            base_snapshot[f"{val_col}_form"] = None
            base_snapshot[f"{val_col}_acceptance_timestamp"] = None
            base_snapshot[f"{val_col}_age_days"] = np.nan
            base_snapshot[f"{val_col}_is_stale"] = False

        base_snapshot["fundamental_has_stale_facts"] = False
        base_snapshot["fundamental_all_facts_stale"] = False

        if self.config.compute_ratios:
            for ratio in [
                "debt_to_assets", "debt_to_equity", "net_margin",
                "roa", "current_ratio", "ocf_to_net_income"
            ]:
                r_col = f"fundamental_ratio_{ratio}"
                base_snapshot[r_col] = np.nan
                base_snapshot[f"{r_col}_missing"] = True

        return base_snapshot

    def compute_snapshots_for_decisions(
        self,
        decision_points: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Takes a DataFrame containing at least ['company_id', 'decision_timestamp']
        and produces point-in-time fundamental features aligned to each decision point.
        """
        if decision_points.empty:
            return pd.DataFrame()

        records = []
        for _, row in decision_points.iterrows():
            cid = str(row["company_id"])
            d_ts = pd.to_datetime(row["decision_timestamp"], utc=True)
            snapshot = self.get_as_of_snapshot(cid, d_ts)
            records.append(snapshot)

        return pd.DataFrame(records, index=decision_points.index)

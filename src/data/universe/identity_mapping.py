"""
Corporate Identity Resolution and Historical Entity Mapping Layer.

Maintains time-aware mappings between trading tickers, canonical company IDs,
SEC Central Index Keys (CIKs), corporate reorganizations, and predecessor lineages.
Guarantees:
1. Immutability of canonical cohort manifest.
2. Explicit provenance and legal filing evidence for all historical mappings.
3. Separation of reporting CIK and current successor CIK.
4. Time-bounded resolution: queries resolve CIK based on observation date.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, date
import logging
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HistoricalEntityMapping:
    """Represents a time-bounded corporate identity mapping with explicit legal provenance."""
    ticker: str
    canonical_company_id: str
    manifest_cik: str
    historical_cik: str
    entity_name: str
    effective_start: str  # YYYY-MM-DD
    effective_end: str    # YYYY-MM-DD
    mapping_type: str     # 'CIK_CORRECTION', 'PREDECESSOR_REORGANIZATION', 'STANDARD'
    evidence_provenance: str


# Authoritative corporate identity exceptions and historical lineages
HISTORICAL_IDENTITY_REGISTRY: List[HistoricalEntityMapping] = [
    # 1. Concho Resources Inc (CXO): Manifest CIK 1390532 is Coral #20 JV; True Concho CIK is 0001358071
    HistoricalEntityMapping(
        ticker="CXO",
        canonical_company_id="US_CIK_0001390532",
        manifest_cik="0001390532",
        historical_cik="0001358071",
        entity_name="CONCHO RESOURCES INC",
        effective_start="2006-02-22",
        effective_end="2021-01-15",
        mapping_type="CIK_CORRECTION",
        evidence_provenance=(
            "SEC EDGAR Form 10-K (2007-2020) and Form 8-K filings verify Concho Resources Inc. "
            "operated under CIK 0001358071 until acquisition by ConocoPhillips in Jan 2021. "
            "Manifest CIK 1390532 corresponds to Coral #20 Joint Venture."
        ),
    ),
    # 2. APA Corporation (APA): Succeeded Apache Corporation (CIK 0000006769) on March 1, 2021
    HistoricalEntityMapping(
        ticker="APA",
        canonical_company_id="US_CIK_0001841666",
        manifest_cik="0001841666",
        historical_cik="0000006769",
        entity_name="APACHE CORP",
        effective_start="1954-12-06",
        effective_end="2021-02-28",
        mapping_type="PREDECESSOR_REORGANIZATION",
        evidence_provenance=(
            "Form 8-K filed 2021-03-01 by APA Corp and Apache Corp confirms holding company reorganization "
            "under DGCL Section 251(g). Apache Corp (CIK 0000006769) stock converted 1:1 into APA Corp "
            "(CIK 0001841666) stock and ticker APA transferred. All 2018-2020 operations filed under CIK 0000006769."
        ),
    ),
    HistoricalEntityMapping(
        ticker="APA",
        canonical_company_id="US_CIK_0001841666",
        manifest_cik="0001841666",
        historical_cik="0001841666",
        entity_name="APA Corp",
        effective_start="2021-03-01",
        effective_end="9999-12-31",
        mapping_type="STANDARD",
        evidence_provenance="Successor holding company post-reorganization.",
    ),
]


class IdentityResolutionEngine:
    """Resolves corporate identifiers dynamically based on observation dates."""

    def __init__(self, cohort_manifest_df: Optional[pd.DataFrame] = None):
        self.cohort_df = cohort_manifest_df
        self._ticker_date_map: Dict[str, List[HistoricalEntityMapping]] = {}
        self._cik_date_map: Dict[str, List[HistoricalEntityMapping]] = {}

        for mapping in HISTORICAL_IDENTITY_REGISTRY:
            tk = mapping.ticker
            if tk not in self._ticker_date_map:
                self._ticker_date_map[tk] = []
            self._ticker_date_map[tk].append(mapping)

            # Also index by historical CIK
            h_cik = mapping.historical_cik
            if h_cik not in self._cik_date_map:
                self._cik_date_map[h_cik] = []
            self._cik_date_map[h_cik].append(mapping)

    def resolve_cik(self, ticker: str, observation_date: str) -> Tuple[str, str, str]:
        """
        Resolves the verified historical CIK for a ticker as of a specific date.
        Returns: (resolved_cik_10digit, entity_name, mapping_type)
        """
        obs_date_str = str(observation_date)[:10]
        mappings = self._ticker_date_map.get(ticker)
        if mappings:
            for m in mappings:
                if m.effective_start <= obs_date_str <= m.effective_end:
                    return m.historical_cik, m.entity_name, m.mapping_type

        # Default fallback to manifest CIK if cohort dataframe is provided
        if self.cohort_df is not None:
            match = self.cohort_df[self.cohort_df["ticker"] == ticker]
            if not match.empty:
                raw_cik = str(match.iloc[0]["cik"]).strip().zfill(10)
                cname = str(match.iloc[0]["company_name"])
                return raw_cik, cname, "STANDARD"

        return "", "", "UNKNOWN"

    def get_canonical_company_id(self, ticker: str) -> Optional[str]:
        """Returns the canonical cohort company_id (preserving manifest identity)."""
        mappings = self._ticker_date_map.get(ticker)
        if mappings:
            return mappings[0].canonical_company_id
        if self.cohort_df is not None:
            match = self.cohort_df[self.cohort_df["ticker"] == ticker]
            if not match.empty:
                return str(match.iloc[0]["company_id"])
        return None

    def get_provenance_record(self, ticker: str) -> Optional[HistoricalEntityMapping]:
        """Returns the historical identity mapping record if an exception exists."""
        mappings = self._ticker_date_map.get(ticker)
        if mappings:
            return mappings[0]
        return None

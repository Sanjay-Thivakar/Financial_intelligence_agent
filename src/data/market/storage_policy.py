"""
License-Aware Storage Policy & Data Governance.

Enforces legal data governance across four distinct data lifecycle layers:
1. RAW_RESPONSE: Exact JSON/CSV responses from provider APIs.
2. NORMALIZED_SERIES: Standardized tabular quote series (Parquet).
3. DERIVED_FEATURES: Non-reversible mathematical transformations (volatility, returns, indicators).
4. MODEL_OUTPUTS: Decisions, weights, SHAP explanations, recommendations.

Distinguishes confirmed permissions from assumptions based on authoritative terms.
"""

from enum import Enum
from pathlib import Path
from typing import Dict, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class DataLayer(str, Enum):
    """Classification of data storage layers with distinct legal governance."""
    RAW_RESPONSE = "raw_response"
    NORMALIZED_SERIES = "normalized_series"
    DERIVED_FEATURES = "derived_features"
    MODEL_OUTPUTS = "model_outputs"


class LicenseStatus(str, Enum):
    """Legal authorization status for data persistence."""
    PERMITTED = "PERMITTED"
    RESTRICTED = "RESTRICTED"
    PROHIBITED = "PROHIBITED"
    UNVERIFIED = "UNVERIFIED"


class StoragePolicy:
    """Evaluates and enforces data persistence rules across providers and tiers."""

    # Provider legal rules matrix: (provider, plan_tier, data_layer) -> (is_permitted, status, rule_reason)
    RULES: Dict[Tuple[str, str, DataLayer], Tuple[bool, LicenseStatus, str]] = {
        ("sec_edgar", "any", DataLayer.RAW_RESPONSE): (
            True, LicenseStatus.PERMITTED, "US Public Domain under 17 U.S.C. § 105; unrestricted archiving permitted"
        ),
        ("sec_edgar", "any", DataLayer.NORMALIZED_SERIES): (
            True, LicenseStatus.PERMITTED, "US Public Domain under 17 U.S.C. § 105; unrestricted local Parquet storage permitted"
        ),
        ("sec_edgar", "any", DataLayer.DERIVED_FEATURES): (
            True, LicenseStatus.PERMITTED, "US Public Domain under 17 U.S.C. § 105; feature extraction unrestricted"
        ),
        ("sec_edgar", "any", DataLayer.MODEL_OUTPUTS): (
            True, LicenseStatus.PERMITTED, "US Public Domain under 17 U.S.C. § 105; unrestricted release"
        ),

        ("tiingo", "starter", DataLayer.RAW_RESPONSE): (
            False, LicenseStatus.PROHIBITED, "Tiingo Starter Terms: Persistent storage prohibited; memory processing only"
        ),
        ("tiingo", "starter", DataLayer.NORMALIZED_SERIES): (
            False, LicenseStatus.PROHIBITED, "Tiingo Starter Terms: Persistent local database/archive prohibited without enterprise license"
        ),
        ("tiingo", "starter", DataLayer.DERIVED_FEATURES): (
            True, LicenseStatus.PERMITTED, "Non-reversible transformative mathematical features for internal research"
        ),
        ("tiingo", "starter", DataLayer.MODEL_OUTPUTS): (
            True, LicenseStatus.PERMITTED, "Model predictions & recommendations are project IP"
        ),

        ("tiingo", "power", DataLayer.RAW_RESPONSE): (
            True, LicenseStatus.PERMITTED, "Tiingo Power Tier: Internal raw caching permitted for subscriber research"
        ),
        ("tiingo", "power", DataLayer.NORMALIZED_SERIES): (
            True, LicenseStatus.PERMITTED, "Tiingo Power Tier: Internal research database permitted during subscription (no public redistribution)"
        ),
        ("tiingo", "power", DataLayer.DERIVED_FEATURES): (
            True, LicenseStatus.PERMITTED, "Internal research permitted; non-reversible"
        ),
        ("tiingo", "power", DataLayer.MODEL_OUTPUTS): (
            True, LicenseStatus.PERMITTED, "Model outputs permitted"
        ),

        ("polygon", "developer", DataLayer.RAW_RESPONSE): (
            True, LicenseStatus.PERMITTED, "Polygon/Massive Developer Terms: Internal caching permitted for research"
        ),
        ("polygon", "developer", DataLayer.NORMALIZED_SERIES): (
            True, LicenseStatus.PERMITTED, "Polygon/Massive Developer Terms: Internal database permitted during active subscription"
        ),
        ("polygon", "developer", DataLayer.DERIVED_FEATURES): (
            True, LicenseStatus.PERMITTED, "Derivative works permitted for internal research"
        ),
        ("polygon", "developer", DataLayer.MODEL_OUTPUTS): (
            True, LicenseStatus.PERMITTED, "Model outputs permitted"
        ),

        ("polygon", "free", DataLayer.RAW_RESPONSE): (
            False, LicenseStatus.PROHIBITED, "Polygon Free Tier: Restricted to 5 req/min, 2-yr history; bulk persistent warehousing prohibited"
        ),
        ("polygon", "free", DataLayer.NORMALIZED_SERIES): (
            False, LicenseStatus.PROHIBITED, "Polygon Free Tier: Persistent warehousing prohibited without paid commercial license"
        ),
        ("polygon", "free", DataLayer.DERIVED_FEATURES): (
            True, LicenseStatus.PERMITTED, "Derivative non-reversible features for internal research"
        ),
        ("polygon", "free", DataLayer.MODEL_OUTPUTS): (
            True, LicenseStatus.PERMITTED, "Model outputs permitted"
        ),

        ("wrds", "academic", DataLayer.RAW_RESPONSE): (
            True, LicenseStatus.PERMITTED, "WRDS Academic License: Internal research caching permitted on authorized institutional infrastructure"
        ),
        ("wrds", "academic", DataLayer.NORMALIZED_SERIES): (
            True, LicenseStatus.PERMITTED, "WRDS Academic License: Internal research database permitted (no public redistribution)"
        ),
        ("wrds", "academic", DataLayer.DERIVED_FEATURES): (
            True, LicenseStatus.PERMITTED, "Academic research feature extraction permitted"
        ),
        ("wrds", "academic", DataLayer.MODEL_OUTPUTS): (
            True, LicenseStatus.PERMITTED, "Model outputs and empirical paper findings permitted"
        ),

        ("yfinance", "unauthorized", DataLayer.RAW_RESPONSE): (
            False, LicenseStatus.PROHIBITED, "Yahoo Finance ToS: Automated scraping & persistent caching prohibited"
        ),
        ("yfinance", "unauthorized", DataLayer.NORMALIZED_SERIES): (
            False, LicenseStatus.PROHIBITED, "Yahoo Finance ToS: Scraping prohibited; unverified rights"
        ),
        ("yfinance", "unauthorized", DataLayer.DERIVED_FEATURES): (
            False, LicenseStatus.PROHIBITED, "Tainted upstream provenance"
        ),
        ("yfinance", "unauthorized", DataLayer.MODEL_OUTPUTS): (
            True, LicenseStatus.PERMITTED, "Model outputs permitted"
        ),

        ("fnspid", "sample", DataLayer.RAW_RESPONSE): (
            False, LicenseStatus.UNVERIFIED, "FNSPID sample raw news persistence unverified; scraped third-party commercial articles lack publisher consent"
        ),
        ("fnspid", "sample", DataLayer.NORMALIZED_SERIES): (
            False, LicenseStatus.UNVERIFIED, "Normalized news text caching unverified without publisher licenses"
        ),
        ("fnspid", "sample", DataLayer.DERIVED_FEATURES): (
            True, LicenseStatus.PERMITTED, "Non-reversible statistical aggregation counts permitted for internal research"
        ),
        ("fnspid", "sample", DataLayer.MODEL_OUTPUTS): (
            True, LicenseStatus.PERMITTED, "Model outputs permitted"
        ),

        ("fnspid", "full_universe", DataLayer.RAW_RESPONSE): (
            False, LicenseStatus.UNVERIFIED, "FNSPID bulk persistent warehousing unverified; 3rd-party commercial news text redistribution prohibited without enterprise rights"
        ),
        ("fnspid", "full_universe", DataLayer.NORMALIZED_SERIES): (
            False, LicenseStatus.UNVERIFIED, "Full-universe raw news persistence unverified"
        ),
        ("fnspid", "full_universe", DataLayer.DERIVED_FEATURES): (
            True, LicenseStatus.PERMITTED, "Non-reversible derived statistical features permitted"
        ),
        ("fnspid", "full_universe", DataLayer.MODEL_OUTPUTS): (
            True, LicenseStatus.PERMITTED, "Model outputs permitted"
        ),
    }

    @classmethod
    def can_persist_locally(
        cls,
        provider: str,
        layer: DataLayer,
        plan_tier: str = "starter",
    ) -> bool:
        """Evaluates whether local persistence is permitted for a given provider, layer, and tier."""
        provider_clean = provider.lower().strip()
        tier_clean = plan_tier.lower().strip()

        # Check explicit rule
        key = (provider_clean, tier_clean, layer)
        if key in cls.RULES:
            return cls.RULES[key][0]

        # Check fallback with "any" tier
        key_any = (provider_clean, "any", layer)
        if key_any in cls.RULES:
            return cls.RULES[key_any][0]

        # By default, unknown providers or layers are restricted/unverified
        return False

    @classmethod
    def evaluate_storage_request(
        cls,
        provider: str,
        layer: DataLayer,
        plan_tier: str = "starter",
    ) -> Tuple[LicenseStatus, str]:
        """Returns a LicenseStatus and explanation for a requested persistence action."""
        provider_clean = provider.lower().strip()
        tier_clean = plan_tier.lower().strip()

        key = (provider_clean, tier_clean, layer)
        if key in cls.RULES:
            entry = cls.RULES[key]
            if len(entry) == 3:
                return entry[1], entry[2]
            permitted, reason = entry
            status = LicenseStatus.PERMITTED if permitted else LicenseStatus.PROHIBITED
            return status, reason

        key_any = (provider_clean, "any", layer)
        if key_any in cls.RULES:
            entry = cls.RULES[key_any]
            if len(entry) == 3:
                return entry[1], entry[2]
            permitted, reason = entry
            status = LicenseStatus.PERMITTED if permitted else LicenseStatus.PROHIBITED
            return status, reason

        return LicenseStatus.UNVERIFIED, f"No verified licensing terms found for provider '{provider}' under tier '{plan_tier}' for {layer}."

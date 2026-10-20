"""
Feature Engineering Configuration and Storage Governance.

Defines configuration parameters for market feature calculations,
fundamental feature extraction, and license-safe storage policy enforcement.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.data.market.storage_policy import DataLayer, LicenseStatus, StoragePolicy


class DecisionTimingMode(str, Enum):
    """
    Defines when decision features are available for trading execution.
    - MARKET_CLOSE: Decision timestamp is aligned with the session market close (16:00 ET -> 20:00 UTC EDT / 21:00 UTC EST).
    - NEXT_SESSION_OPEN: Decision timestamp is aligned with the next session market open (09:30 ET -> 13:30 UTC EDT / 14:30 UTC EST).
    """
    MARKET_CLOSE = "market_close"
    NEXT_SESSION_OPEN = "next_session_open"


class PersistenceMode(str, Enum):
    """Execution storage mode for derived features."""
    IN_MEMORY = "in_memory"
    DISK_PARQUET = "disk_parquet"


@dataclass
class FeatureStorageConfig:
    """
    Storage governance configuration for feature engineering.
    Conservative by default: requires verified user authorization and
    conformance with provider license terms before permitting disk persistence.
    """
    provider: str = "tiingo"
    plan_tier: str = "starter"  # Conservative default: starter/free plan
    storage_authorized: bool = False  # Explicit user authorization required for disk writes
    persistence_mode: PersistenceMode = PersistenceMode.IN_MEMORY
    output_dir: Optional[Path] = None

    def validate_persistence(self, layer: DataLayer = DataLayer.DERIVED_FEATURES) -> Tuple[bool, str]:
        """
        Validates whether derived features can be persisted to disk.
        Returns (is_permitted, reason).
        """
        if self.persistence_mode == PersistenceMode.IN_MEMORY:
            return True, "In-memory mode active; transient processing permitted without disk writes."

        if not self.storage_authorized:
            return False, (
                "Disk persistence rejected: explicit user storage authorization is FALSE. "
                "Feature outputs must remain in-memory."
            )

        # Check provider licensing terms via StoragePolicy
        is_legal = StoragePolicy.can_persist_locally(self.provider, layer, self.plan_tier)
        status, reason = StoragePolicy.evaluate_storage_request(self.provider, layer, self.plan_tier)

        if not is_legal:
            return False, f"Disk persistence prohibited by {self.provider} ({self.plan_tier}) terms: {reason}"

        return True, f"Disk persistence permitted: {reason}"


@dataclass
class MarketFeatureConfig:
    """Configurable lookback windows and settings for market feature engineering."""
    return_windows: Tuple[int, ...] = (1, 5, 21)
    volatility_windows: Tuple[int, ...] = (5, 21, 63)
    momentum_windows: Tuple[int, ...] = (5, 21, 63, 126)
    rolling_mean_windows: Tuple[int, ...] = (20, 50, 200)
    rsi_window: int = 14
    volume_window: int = 20
    annualization_factor: float = 252.0  # Number of US trading days per year
    decision_timing: DecisionTimingMode = DecisionTimingMode.MARKET_CLOSE
    pre_open_cutoff_minutes: int = 0  # Pre-open cutoff buffer in minutes (0 = unbuffered 09:30 open; >0 = pre-open cutoff)


# Default mapping from canonical concept to priority list of SEC XBRL GAAP tags
DEFAULT_CONCEPT_MAPPINGS: Dict[str, List[str]] = {
    "revenue": [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
    ],
    "net_income": [
        "NetIncomeLoss",
        "ProfitLoss",
    ],
    "operating_income": [
        "OperatingIncomeLoss",
    ],
    "total_assets": [
        "Assets",
    ],
    "total_liabilities": [
        "Liabilities",
    ],
    "current_assets": [
        "AssetsCurrent",
    ],
    "current_liabilities": [
        "LiabilitiesCurrent",
    ],
    "stockholders_equity": [
        "StockholdersEquity",
    ],
    "operating_cash_flow": [
        "NetCashProvidedByUsedInOperatingActivities",
    ],
    "long_term_debt": [
        "LongTermDebtNoncurrent",
        "LongTermDebt",
    ],
    "short_term_debt": [
        "DebtCurrent",
        "ShortTermBorrowings",
    ],
    "diluted_eps": [
        "EarningsPerShareDiluted",
    ],
}


@dataclass
class FundamentalFeatureConfig:
    """Configuration for point-in-time fundamental feature extraction."""
    concept_mappings: Dict[str, List[str]] = field(default_factory=lambda: DEFAULT_CONCEPT_MAPPINGS)
    compute_ratios: bool = True
    max_staleness_days: int = 400  # Max age of financial filing before considered excessively stale


@dataclass
class NewsFeatureConfig:
    """
    Configuration for point-in-time financial news baseline feature engineering.
    Guarantees:
    - Trailing lookback windows specified in calendar days.
    - Strict point-in-time availability prevents look-ahead leakage.
    - Purely factual and statistical metrics (no invented sentiment scores or return claims).
    """
    trailing_windows: Tuple[int, ...] = (1, 3, 7, 14, 30)
    allow_date_only: bool = True  # If True, date-only articles eligible only on subsequent dates (published_date < decision_date)
    require_intraday_time: bool = False  # If True, strictly rejects all date-only articles
    recency_max_days: int = 30  # Max lookback window for recency calculation in hours


@dataclass
class SECEventFeatureConfig:
    """
    Configuration for SEC Form 8-K point-in-time corporate event feature engineering.
    Guarantees:
    - Conservative dissemination buffer (default 5 minutes).
    - Filing eligible only when acceptance_timestamp + buffer <= decision_timestamp.
    - Factual event counts and indicators only (no sentiment or NLP).
    """
    dissemination_buffer_minutes: int = 5
    window_sessions: int = 5
    target_items: Tuple[str, ...] = ("1.01", "2.02", "5.02", "7.01", "8.01")
    earnings_item: str = "2.02"
    recency_unit: str = "calendar_days"  # Unit: floating-point calendar days since acceptance



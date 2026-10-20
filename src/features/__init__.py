"""
Feature Engineering Package.

Provides point-in-time, license-safe technical and fundamental feature engineering
and temporal alignment for financial intelligence modeling.
"""

from src.features.config import (
    DecisionTimingMode,
    PersistenceMode,
    FeatureStorageConfig,
    MarketFeatureConfig,
    FundamentalFeatureConfig,
    NewsFeatureConfig,
)
from src.features.calendar import MarketCalendar
from src.features.market import MarketFeatureEngine
from src.features.fundamental import FundamentalFeatureEngine
from src.features.news import NewsFeatureEngine
from src.features.alignment import TemporalAligner, LookaheadLeakageError
from src.features.storage import FeatureStorageManager, StorageAuthorizationError

from src.features.dataset import (
    DatasetBuildConfig,
    DatasetCoverageReport,
    DatasetBuildResult,
    UnifiedDatasetBuilder,
    DatasetIntegrityError,
)

__all__ = [
    "MarketCalendar",
    "DecisionTimingMode",
    "PersistenceMode",
    "FeatureStorageConfig",
    "MarketFeatureConfig",
    "FundamentalFeatureConfig",
    "NewsFeatureConfig",
    "MarketFeatureEngine",
    "FundamentalFeatureEngine",
    "NewsFeatureEngine",
    "TemporalAligner",
    "LookaheadLeakageError",
    "FeatureStorageManager",
    "StorageAuthorizationError",
    "DatasetBuildConfig",
    "DatasetCoverageReport",
    "DatasetBuildResult",
    "UnifiedDatasetBuilder",
    "DatasetIntegrityError",
]

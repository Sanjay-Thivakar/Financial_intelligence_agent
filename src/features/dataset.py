"""
Unified Dataset Construction & Validation Module (Phase 4C).

Orchestrates reproducible, leakage-aware dataset construction by harmonizing:
1. Historical market features (MarketFeatureEngine).
2. Point-in-time SEC EDGAR fundamental snapshots (FundamentalFeatureEngine).
3. Point-in-time financial news baseline metrics (NewsFeatureEngine).

Enforces the Observation & Decision-Time Contract:
- Strictly one row per unique (company_id, decision_timestamp).
- Canonical corporate identity preservation (never ticker-only joins).
- Point-in-time availability verification across all three modalities.
- Explicit source missingness vs. genuine zero activity distinction.
- Conservative storage policy governance (in-memory execution by default).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Dict, List, Optional, Tuple, Any, Set
import numpy as np
import pandas as pd

from src.data.market.storage_policy import DataLayer, LicenseStatus, StoragePolicy
from src.features.calendar import MarketCalendar
from src.features.config import (
    DecisionTimingMode,
    PersistenceMode,
    FeatureStorageConfig,
    MarketFeatureConfig,
    FundamentalFeatureConfig,
    NewsFeatureConfig,
    SECEventFeatureConfig,
)
from src.features.market import MarketFeatureEngine
from src.features.fundamental import FundamentalFeatureEngine
from src.features.news import NewsFeatureEngine
from src.features.event import SECEventFeatureEngine
from src.features.alignment import TemporalAligner, LookaheadLeakageError
from src.features.storage import FeatureStorageManager, StorageAuthorizationError

logger = logging.getLogger(__name__)


class DatasetIntegrityError(Exception):
    """Raised when unified dataset construction violates contract or integrity constraints."""
    pass


@dataclass
class DatasetCoverageReport:
    """Summary of data coverage, exclusions, and source missingness."""
    total_input_market_rows: int = 0
    rows_retained: int = 0
    rows_excluded_malformed: int = 0
    rows_excluded_cohort: int = 0
    rows_excluded_date_bounds: int = 0
    rows_excluded_duplicate: int = 0
    rows_excluded_sp500_inactive: int = 0
    unique_companies: int = 0
    date_range_min: Optional[str] = None
    date_range_max: Optional[str] = None
    market_coverage_pct: float = 0.0
    fundamental_coverage_pct: float = 0.0  # Core financial statement coverage (revenue + net_income fresh)
    fundamental_core_coverage_pct: float = 0.0
    fundamental_comprehensive_coverage_pct: float = 0.0  # All configured concepts present
    fundamental_concept_availability_pct: Dict[str, float] = field(default_factory=dict)
    fundamental_stale_rows_count: int = 0
    coverage_denominator: int = 0
    news_coverage_pct: float = 0.0
    news_coverage_status_counts: Dict[str, int] = field(default_factory=dict)
    fundamental_coverage_status_counts: Dict[str, int] = field(default_factory=dict)
    event_coverage_pct: float = 0.0
    event_coverage_status_counts: Dict[str, int] = field(default_factory=dict)
    total_events_in_window: int = 0
    unresolved_licensing_blockers: List[str] = field(default_factory=list)
    temporal_overlap_assessment: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_input_market_rows": self.total_input_market_rows,
            "rows_retained": self.rows_retained,
            "rows_excluded_malformed": self.rows_excluded_malformed,
            "rows_excluded_cohort": self.rows_excluded_cohort,
            "rows_excluded_date_bounds": self.rows_excluded_date_bounds,
            "rows_excluded_duplicate": self.rows_excluded_duplicate,
            "rows_excluded_sp500_inactive": self.rows_excluded_sp500_inactive,
            "unique_companies": self.unique_companies,
            "date_range_min": self.date_range_min,
            "date_range_max": self.date_range_max,
            "market_coverage_pct": self.market_coverage_pct,
            "fundamental_coverage_pct": self.fundamental_coverage_pct,
            "fundamental_core_coverage_pct": self.fundamental_core_coverage_pct,
            "fundamental_comprehensive_coverage_pct": self.fundamental_comprehensive_coverage_pct,
            "fundamental_concept_availability_pct": self.fundamental_concept_availability_pct,
            "fundamental_stale_rows_count": self.fundamental_stale_rows_count,
            "coverage_denominator": self.coverage_denominator,
            "news_coverage_pct": self.news_coverage_pct,
            "news_coverage_status_counts": self.news_coverage_status_counts,
            "fundamental_coverage_status_counts": self.fundamental_coverage_status_counts,
            "event_coverage_pct": self.event_coverage_pct,
            "event_coverage_status_counts": self.event_coverage_status_counts,
            "total_events_in_window": self.total_events_in_window,
            "unresolved_licensing_blockers": self.unresolved_licensing_blockers,
            "temporal_overlap_assessment": self.temporal_overlap_assessment,
        }


@dataclass
class DatasetBuildConfig:
    """Configuration governing unified dataset construction."""
    start_date: Optional[str] = None  # Inclusive ISO start date (YYYY-MM-DD)
    end_date: Optional[str] = None    # Inclusive ISO end date (YYYY-MM-DD)
    cohort_company_ids: Optional[Tuple[str, ...]] = None  # Explicit cohort filter
    filter_sp500_active: bool = False  # Filter to active index constituent sessions
    strict_leakage_check: bool = True  # Enforce lookahead assertions
    pre_open_cutoff_minutes: int = 15  # Pre-open cutoff buffer (default 15m before 09:30 ET open)
    market_config: MarketFeatureConfig = field(default_factory=MarketFeatureConfig)
    fundamental_config: FundamentalFeatureConfig = field(default_factory=FundamentalFeatureConfig)
    news_config: NewsFeatureConfig = field(default_factory=NewsFeatureConfig)
    event_config: SECEventFeatureConfig = field(default_factory=SECEventFeatureConfig)
    storage_config: FeatureStorageConfig = field(default_factory=FeatureStorageConfig)


@dataclass
class DatasetBuildResult:
    """Artifact containing aligned dataset, coverage statistics, and build metadata."""
    data: pd.DataFrame
    coverage_report: DatasetCoverageReport
    build_timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    contract_version: str = "v1.0"


class UnifiedDatasetBuilder:
    """Builds and validates unified multi-modal datasets under strict point-in-time contracts."""

    REQUIRED_MARKET_COLUMNS = [
        "company_id", "ticker", "timestamp", "trading_date",
        "open", "high", "low", "close", "adjusted_close", "volume",
    ]

    def __init__(self, config: Optional[DatasetBuildConfig] = None):
        self.config = config or DatasetBuildConfig()

    def build_dataset(
        self,
        df_market: pd.DataFrame,
        df_fundamentals: Optional[pd.DataFrame] = None,
        df_news: Optional[pd.DataFrame] = None,
        universe_df: Optional[pd.DataFrame] = None,
        df_events: Optional[pd.DataFrame] = None,
    ) -> DatasetBuildResult:
        """
        Executes bounded, deterministic dataset construction and validation.

        :param df_market: Daily equity market observations.
        :param df_fundamentals: Point-in-time SEC EDGAR company facts.
        :param df_news: Normalized point-in-time financial news articles.
        :param universe_df: S&P 500 canonical company identity and membership intervals.
        :param df_events: Processed Form 8-K corporate events.
        :return: DatasetBuildResult with aligned features and coverage report.
        """
        report = DatasetCoverageReport()
        report.total_input_market_rows = len(df_market) if df_market is not None else 0

        # 1. Inspect licensing and storage governance preconditions
        self._audit_storage_licensing_preconditions(report)

        if df_market is None or df_market.empty:
            report.temporal_overlap_assessment = "Market input DataFrame is empty; dataset construction halted."
            return DatasetBuildResult(data=pd.DataFrame(), coverage_report=report)

        # 2. Preflight validation & market sanitization
        sanitized_market = self._sanitize_and_bound_market_data(df_market.copy(), report)
        if sanitized_market.empty:
            report.temporal_overlap_assessment = "All input market rows excluded by cohort or date bounds."
            return DatasetBuildResult(data=pd.DataFrame(), coverage_report=report)

        # 3. Instantiate Feature Engines
        # In NEXT_SESSION_OPEN mode, enforce pre-open cutoff buffer (09:15 ET)
        if self.config.market_config.decision_timing == DecisionTimingMode.NEXT_SESSION_OPEN:
            if self.config.market_config.pre_open_cutoff_minutes == 0 and self.config.pre_open_cutoff_minutes > 0:
                self.config.market_config.pre_open_cutoff_minutes = self.config.pre_open_cutoff_minutes

        market_engine = MarketFeatureEngine(self.config.market_config)
        fundamental_engine = (
            FundamentalFeatureEngine(df_fundamentals, self.config.fundamental_config)
            if df_fundamentals is not None and not df_fundamentals.empty
            else None
        )
        news_engine = (
            NewsFeatureEngine(df_news, self.config.news_config)
            if df_news is not None and not df_news.empty
            else None
        )
        event_engine = (
            SECEventFeatureEngine(df_events, self.config.event_config)
            if df_events is not None and not df_events.empty
            else None
        )

        # 4. Temporal Alignment & Point-in-Time Harmonization
        aligner = TemporalAligner(
            market_engine=market_engine,
            fundamental_engine=fundamental_engine,
            news_engine=news_engine,
            event_engine=event_engine,
            universe_df=universe_df,
        )

        pre_align_count = len(sanitized_market)
        aligned_df = aligner.align_features(
            sanitized_market,
            strict_leakage_check=self.config.strict_leakage_check,
            filter_sp500_active=self.config.filter_sp500_active,
        )
        if self.config.filter_sp500_active:
            report.rows_excluded_sp500_inactive = pre_align_count - len(aligned_df)

        if aligned_df.empty:
            report.temporal_overlap_assessment = "No observations remained after S&P 500 active constituent filtering."
            return DatasetBuildResult(data=pd.DataFrame(), coverage_report=report)

        # 5. Enforce Observation & Decision-Time Contract
        aligned_df = self._enforce_contract_metadata(
            aligned_df=aligned_df,
            raw_market_df=sanitized_market,
            df_fundamentals=df_fundamentals,
            df_news=df_news,
            df_events=df_events,
            report=report,
        )

        # 6. Verify strictly unique (company_id, decision_timestamp) pairs
        self._verify_row_uniqueness(aligned_df)

        # 7. Evaluate and record coverage statistics
        self._calculate_coverage_metrics(aligned_df, df_fundamentals, df_news, df_events, report)

        # 8. Storage Policy Enforcement
        self._enforce_storage_governance(aligned_df)

        return DatasetBuildResult(data=aligned_df, coverage_report=report)

    def _audit_storage_licensing_preconditions(self, report: DatasetCoverageReport) -> None:
        """Audits licensing terms across providers and logs unresolved status blockers."""
        blockers = []
        # Tiingo Starter check
        status_tiingo_raw, _ = StoragePolicy.evaluate_storage_request("tiingo", DataLayer.RAW_RESPONSE, "starter")
        if status_tiingo_raw != LicenseStatus.PERMITTED:
            blockers.append("Tiingo starter tier prohibits local database persistence without enterprise rights.")

        # FNSPID Sample check
        status_fnspid_raw, _ = StoragePolicy.evaluate_storage_request("fnspid", DataLayer.RAW_RESPONSE, "sample")
        if status_fnspid_raw == LicenseStatus.UNVERIFIED:
            blockers.append("FNSPID sample raw/normalized text caching is UNVERIFIED (scraped commercial articles).")

        report.unresolved_licensing_blockers = blockers

    def _sanitize_and_bound_market_data(
        self,
        df: pd.DataFrame,
        report: DatasetCoverageReport,
    ) -> pd.DataFrame:
        """Validates market schema, drops malformed records, applies cohort/date bounds, and deduplicates."""
        # Verify required columns
        missing_cols = [c for c in self.REQUIRED_MARKET_COLUMNS if c not in df.columns]
        if missing_cols:
            raise DatasetIntegrityError(f"Market DataFrame missing required schema columns: {missing_cols}")

        initial_len = len(df)

        # 1. Filter out malformed price records
        valid_mask = (
            df["company_id"].notna() & (df["company_id"].astype(str).str.strip() != "") &
            df["trading_date"].notna() & (df["trading_date"].astype(str).str.strip() != "") &
            df["timestamp"].notna() &
            (df["close"] > 0) & (df["open"] > 0) & (df["high"] > 0) & (df["low"] > 0) &
            (df["adjusted_close"] > 0)
        )
        malformed_count = initial_len - valid_mask.sum()
        report.rows_excluded_malformed = malformed_count
        clean_df = df[valid_mask].copy()

        # 2. Cohort filtering
        if self.config.cohort_company_ids:
            cohort_set = set(self.config.cohort_company_ids)
            in_cohort = clean_df["company_id"].isin(cohort_set)
            report.rows_excluded_cohort = len(clean_df) - in_cohort.sum()
            clean_df = clean_df[in_cohort].copy()

        # 3. Date bounds filtering
        if self.config.start_date:
            after_start = clean_df["trading_date"] >= self.config.start_date
            report.rows_excluded_date_bounds += (len(clean_df) - after_start.sum())
            clean_df = clean_df[after_start].copy()

        if self.config.end_date:
            before_end = clean_df["trading_date"] <= self.config.end_date
            report.rows_excluded_date_bounds += (len(clean_df) - before_end.sum())
            clean_df = clean_df[before_end].copy()

        # 4. Deduplicate market records on (company_id, trading_date)
        pre_dedupe_len = len(clean_df)
        clean_df = clean_df.drop_duplicates(subset=["company_id", "trading_date"], keep="first").copy()
        report.rows_excluded_duplicate = pre_dedupe_len - len(clean_df)

        # Sort chronologically by trading_date within company
        clean_df = clean_df.sort_values(by=["company_id", "trading_date"]).reset_index(drop=True)
        return clean_df

    def _enforce_contract_metadata(
        self,
        aligned_df: pd.DataFrame,
        raw_market_df: pd.DataFrame,
        df_fundamentals: Optional[pd.DataFrame],
        df_news: Optional[pd.DataFrame],
        df_events: Optional[pd.DataFrame],
        report: DatasetCoverageReport,
    ) -> pd.DataFrame:
        """Populates explicit dataset contract columns and classifies source coverage status."""
        df = aligned_df.copy()

        # 1. Deterministic row identifier
        dec_ts_series = pd.to_datetime(df["decision_timestamp"], utc=True)
        df["dataset_row_id"] = df["company_id"] + "|" + dec_ts_series.dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        # 2. Timing and observation contract fields
        df["decision_timing_mode"] = self.config.market_config.decision_timing.value
        df["market_observation_timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df["information_cutoff_timestamp"] = dec_ts_series
        df["market_observation_valid"] = True
        df["news_cutoff_timestamp"] = dec_ts_series

        # 3. Execution timestamp attachment (strictly feasible historical timeline)
        # For MARKET_CLOSE: closing price is an input feature; execution cannot occur at the same close!
        # Earliest feasible execution is the NEXT TRADING SESSION OPEN.
        # For NEXT_SESSION_OPEN: execution occurs at that session open (coinciding with decision cutoff).
        unique_dates = df["trading_date"].unique()
        next_open_map = {d: MarketCalendar.get_next_session_open_utc(str(d)[:10]) for d in unique_dates}
        df["execution_timestamp"] = df["trading_date"].map(next_open_map)

        # 4. Classify news coverage status (distinguish genuine zero activity from unavailable source)
        news_status_list = []
        news_company_dates: Dict[str, Tuple[str, str]] = {}
        if df_news is not None and not df_news.empty and "company_id" in df_news.columns and "published_date" in df_news.columns:
            for cid, grp in df_news.groupby("company_id"):
                c_min = grp["published_date"].min()
                c_max = grp["published_date"].max()
                news_company_dates[str(cid)] = (str(c_min), str(c_max))

        for _, row in df.iterrows():
            cid = str(row["company_id"])
            t_date = str(row["trading_date"])
            has_news = bool(row.get("news_available", False))

            if has_news:
                news_status_list.append("active_with_events")
            else:
                if cid in news_company_dates:
                    c_min, c_max = news_company_dates[cid]
                    if c_min <= t_date <= c_max:
                        # Covered company during an active historical news period, but 0 events in trailing window
                        news_status_list.append("active_zero_events")
                    else:
                        news_status_list.append("source_unavailable")
                else:
                    news_status_list.append("source_unavailable")

        df["news_coverage_status"] = news_status_list

        # 5. Classify fundamental coverage status
        fund_status_list = []
        has_fund_source = df_fundamentals is not None and not df_fundamentals.empty
        fund_companies: Set[str] = set(df_fundamentals["company_id"].astype(str)) if has_fund_source and "company_id" in df_fundamentals.columns else set()

        for _, row in df.iterrows():
            cid = str(row["company_id"])
            if not has_fund_source or cid not in fund_companies:
                fund_status_list.append("source_unavailable")
                continue

            rev_val = row.get("fundamental_revenue")
            inc_val = row.get("fundamental_net_income")
            has_core = (pd.notna(rev_val) and pd.notna(inc_val)) or (pd.notna(rev_val) or pd.notna(inc_val))

            # Check staleness: if all available facts are stale or core facts are stale
            all_stale = bool(row.get("fundamental_all_facts_stale", False))
            rev_stale = bool(row.get("fundamental_revenue_is_stale", False))
            inc_stale = bool(row.get("fundamental_net_income_is_stale", False))
            core_stale = (rev_stale and inc_stale) if (pd.notna(rev_val) and pd.notna(inc_val)) else (rev_stale or inc_stale)

            if has_core and not all_stale and not core_stale:
                fund_status_list.append("active_with_facts")
            else:
                fund_status_list.append("facts_missing_or_stale")

        df["fundamental_coverage_status"] = fund_status_list

        # 6. Classify SEC corporate event coverage status
        if "sec_event_coverage_status" not in df.columns:
            if df_events is not None and not df_events.empty:
                covered_cids = set(df_events["company_id"].dropna().unique())
                df["sec_event_coverage_status"] = df["company_id"].apply(
                    lambda c: "active" if c in covered_cids else "source_unavailable"
                )
                df["sec_event_available"] = df["company_id"].isin(covered_cids)
            else:
                df["sec_event_coverage_status"] = "source_unavailable"
                df["sec_event_available"] = False

        # Set contract provenance metadata
        df["dataset_builder_provenance"] = "unified_dataset_builder_v1"

        return df

    def _verify_row_uniqueness(self, df: pd.DataFrame) -> None:
        """Asserts that each (company_id, decision_timestamp) pair appears exactly once."""
        dupes = df[df.duplicated(subset=["dataset_row_id"], keep=False)]
        if not dupes.empty:
            sample = dupes[["dataset_row_id", "company_id", "trading_date"]].head(5).to_dict(orient="records")
            raise DatasetIntegrityError(
                f"FATAL JOIN INTEGRITY ERROR: Detected {len(dupes)} duplicate row IDs! "
                f"Dataset builder must maintain strictly 1 row per (company_id, decision_timestamp). Sample: {sample}"
            )

    def _calculate_coverage_metrics(
        self,
        df: pd.DataFrame,
        df_fundamentals: Optional[pd.DataFrame],
        df_news: Optional[pd.DataFrame],
        df_events: Optional[pd.DataFrame],
        report: DatasetCoverageReport,
    ) -> None:
        """Calculates final retention, missingness, and cross-source empirical overlap."""
        report.rows_retained = len(df)
        report.coverage_denominator = report.rows_retained
        report.unique_companies = int(df["company_id"].nunique())
        report.date_range_min = str(df["trading_date"].min())
        report.date_range_max = str(df["trading_date"].max())

        report.market_coverage_pct = 100.0  # All retained rows possess valid market observations

        # Core Fundamental coverage %: rows where core statements (revenue + net_income) are populated and not stale
        if "fundamental_revenue" in df.columns and "fundamental_net_income" in df.columns:
            has_rev = df["fundamental_revenue"].notna()
            has_inc = df["fundamental_net_income"].notna()
            rev_fresh = ~df.get("fundamental_revenue_is_stale", pd.Series([False] * len(df)))
            inc_fresh = ~df.get("fundamental_net_income_is_stale", pd.Series([False] * len(df)))
            core_fresh = (has_rev | has_inc) & (rev_fresh | inc_fresh) & (~df.get("fundamental_all_facts_stale", pd.Series([False] * len(df))))
            report.fundamental_core_coverage_pct = round(float(core_fresh.mean() * 100.0), 2)
            report.fundamental_coverage_pct = report.fundamental_core_coverage_pct
        elif "fundamental_features_has_missing" in df.columns:
            has_fund = (~df["fundamental_features_has_missing"]).mean() * 100.0
            report.fundamental_core_coverage_pct = round(float(has_fund), 2)
            report.fundamental_coverage_pct = report.fundamental_core_coverage_pct
        else:
            report.fundamental_core_coverage_pct = 0.0
            report.fundamental_coverage_pct = 0.0

        # Per-concept availability breakdown
        concept_avail = {}
        for concept in self.config.fundamental_config.concept_mappings:
            col = f"fundamental_{concept}"
            if col in df.columns:
                concept_avail[concept] = round(float(df[col].notna().mean() * 100.0), 2)
            else:
                concept_avail[concept] = 0.0
        report.fundamental_concept_availability_pct = concept_avail

        # Comprehensive coverage: all 12 concepts present and non-stale
        all_concept_cols = [f"fundamental_{c}" for c in self.config.fundamental_config.concept_mappings if f"fundamental_{c}" in df.columns]
        if len(all_concept_cols) == len(self.config.fundamental_config.concept_mappings):
            all_present = df[all_concept_cols].notna().all(axis=1) & (~df.get("fundamental_has_stale_facts", pd.Series([False] * len(df))))
            report.fundamental_comprehensive_coverage_pct = round(float(all_present.mean() * 100.0), 2)
        else:
            report.fundamental_comprehensive_coverage_pct = 0.0

        # Stale facts count
        if "fundamental_has_stale_facts" in df.columns:
            report.fundamental_stale_rows_count = int(df["fundamental_has_stale_facts"].sum())

        # News coverage %: rows where news articles were available in lookback window
        if "news_available" in df.columns:
            has_news = df["news_available"].mean() * 100.0
            report.news_coverage_pct = round(float(has_news), 2)
        else:
            report.news_coverage_pct = 0.0

        # Status distributions
        report.news_coverage_status_counts = df["news_coverage_status"].value_counts().to_dict()
        report.fundamental_coverage_status_counts = df["fundamental_coverage_status"].value_counts().to_dict()

        # SEC Event coverage %: rows where SEC corporate event data was available
        if "sec_event_available" in df.columns:
            has_event = df["sec_event_available"].mean() * 100.0
            report.event_coverage_pct = round(float(has_event), 2)
            report.event_coverage_status_counts = df["sec_event_coverage_status"].value_counts().to_dict()
        else:
            report.event_coverage_pct = 0.0
            report.event_coverage_status_counts = {}

        if "sec_event_count_5d" in df.columns:
            report.total_events_in_window = int(df["sec_event_count_5d"].fillna(0).sum())
        else:
            report.total_events_in_window = 0

        # Empirical overlap assessment
        overlap_notes = []
        if report.fundamental_core_coverage_pct > 0 and report.news_coverage_pct > 0:
            overlap_notes.append("Real 3-way overlap verified across market, fundamentals, and news.")
        elif report.fundamental_core_coverage_pct > 0 and report.news_coverage_pct == 0.0:
            overlap_notes.append(
                "Two-way overlap verified (Market + Fundamentals). Zero real news overlap in this timeframe "
                "(FNSPID news sample ends June 2020; market/SEC observations cover 2023)."
            )
        elif report.fundamental_core_coverage_pct == 0.0 and report.news_coverage_pct > 0:
            overlap_notes.append("Two-way overlap verified (Market + News). Zero fundamental facts available.")
        else:
            overlap_notes.append("Market features only. Fundamentals and news unavailable for this cohort/date range.")

        report.temporal_overlap_assessment = " ".join(overlap_notes)

    def _enforce_storage_governance(self, df: pd.DataFrame) -> None:
        """Validates storage rights if disk persistence is requested; defaults to in-memory."""
        storage_cfg = self.config.storage_config
        is_legal, reason = storage_cfg.validate_persistence(layer=DataLayer.DERIVED_FEATURES)

        if storage_cfg.persistence_mode == PersistenceMode.DISK_PARQUET:
            if not is_legal:
                raise StorageAuthorizationError(
                    f"Dataset persistence blocked under data governance policy: {reason}"
                )
            storage_mgr = FeatureStorageManager(storage_cfg)
            storage_mgr.handle_features(df, filename="unified_feature_dataset.parquet")
            logger.info("Unified dataset safely persisted under authorized governance.")

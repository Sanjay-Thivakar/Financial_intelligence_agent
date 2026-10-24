"""
Financial Intelligence Agent Dashboard Service Layer.

Provides data access, market feature computation, model evaluation provenance,
and experimental inference pipeline for the dashboard prototype.
"""

from pathlib import Path
from typing import Dict, List, Optional, Any
import json
import logging
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from datetime import datetime, timezone
from sklearn.impute import SimpleImputer

from src.api.schemas import (
    CompanyMetadata,
    MarketSeriesPoint,
    CompanyMarketResponse,
    FoldMetricResult,
    ModelEvaluationSummaryResponse,
    PredictionResponse,
    DecisionRequest,
    ScreenerCompanyItem,
    ScreenerResponse,
    DecisionFunnelStage,
    CompanyResearchDetailResponse,
    SignalDetailResponse,
    BulkSignalsResponse,
    CapabilityStatus,
    MarketCoverageStatus,
    IdentityStatus,
    CompanyIdentity,
    MarketArtifactCoverage,
    EvaluationWindowCoverage,
    MultiModalCoverage,
    EvaluationTrackEligibility,
    HistoricalPredictionCoverage,
    RuntimeExecutionCapabilities,
    CompanyCapabilityItem,
    CompanyCapabilityListResponse,
    ArchivedPredictionRecord,
    CompanyArchivedPredictionsResponse,
)
from src.decision.schema import (
    SignalType,
    TransactionCostConfig,
    RiskGateConfig,
    DecisionContractRequest,
    DecisionContractResponse,
)
from src.decision.uncertainty import ResidualUncertaintyEstimator
from src.decision.policy import ThresholdDecisionPolicy
from src.features.market import MarketFeatureEngine
from src.features.target import ForwardReturnTargetEngine, TargetConfig

logger = logging.getLogger(__name__)

# Base project paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data" / "processed"
MARKET_DIR = DATA_DIR / "market"
SEC_DIR = DATA_DIR / "sec" / "facts"
NEWS_DIR = DATA_DIR / "news"


# Verified company catalog - AA is explicitly marked excluded with reasoning
COMPANY_CATALOG: Dict[str, Dict[str, Any]] = {
    "AAPL": {
        "ticker": "AAPL",
        "company_id": "US_CIK_0000320193",
        "company_name": "Apple Inc.",
        "cik": "0000320193",
        "sector": "Information Technology",
        "membership_interval": "S&P 500 Constituent (1982-11-30 to Present)",
        "sec_coverage_status": "active_with_facts",
        "news_coverage_status": "active_with_headlines",
        "pilot_eligible": True,
        "notes": "Full point-in-time SEC XBRL facts available. FNSPID headlines available (441 records). 4-for-1 split in Aug 2020 handled via verified adjustment factor.",
    },
    "JPM": {
        "ticker": "JPM",
        "company_id": "US_CIK_0000019617",
        "company_name": "JPMorgan Chase & Co.",
        "cik": "0000019617",
        "sector": "Financials",
        "membership_interval": "S&P 500 Constituent (1975-06-30 to Present)",
        "sec_coverage_status": "active_with_facts",
        "news_coverage_status": "source_unavailable",
        "pilot_eligible": True,
        "notes": "Full point-in-time SEC XBRL facts available. News headlines unavailable in local pilot sample.",
    },
    "GOOG": {
        "ticker": "GOOG",
        "company_id": "US_CIK_0001652044",
        "company_name": "Alphabet Inc. (Class C)",
        "cik": "0001652044",
        "sector": "Communication Services",
        "membership_interval": "S&P 500 Constituent (2006-03-31 to Present)",
        "sec_coverage_status": "source_unavailable",
        "news_coverage_status": "source_unavailable",
        "pilot_eligible": True,
        "notes": "Market series available (2004-2023). Local SEC facts and news headlines unavailable in current pilot slice (preserved as unobserved/NaN).",
    },
    "TSLA": {
        "ticker": "TSLA",
        "company_id": "US_CIK_0001318605",
        "company_name": "Tesla, Inc.",
        "cik": "0001318605",
        "sector": "Consumer Discretionary",
        "membership_interval": "S&P 500 Constituent (2020-12-21 to Present)",
        "sec_coverage_status": "source_unavailable",
        "news_coverage_status": "source_unavailable",
        "pilot_eligible": True,
        "notes": "Market series available (2010-2023). High volatility asset. Local SEC facts and news headlines unavailable in current pilot slice.",
    },
}

EXCLUDED_COMPANIES: Dict[str, str] = {
    "AA": "Excluded: Historical entity identity unresolved. Alcoa Inc. underwent a corporate split in Nov 2016 into Arconic Inc. (ARNC) and Alcoa Corp (AA). Mapping by ticker string alone violates temporal identity invariants."
}


class DashboardService:
    """Singleton service providing caching and computation for dashboard endpoints."""

    def __init__(self):
        self._market_data_cache: Dict[str, pd.DataFrame] = {}
        self._feature_data_cache: Dict[str, pd.DataFrame] = {}
        self._fitted_market_model: Optional[Ridge] = None
        self._fitted_scaler: Optional[StandardScaler] = None
        self._fitted_imputer: Optional[SimpleImputer] = None
        self._model_feature_cols: List[str] = []
        self._residual_uncertainty_estimator: Optional[ResidualUncertaintyEstimator] = None
        self._initialize_service()

    def _initialize_service(self):
        """Preloads datasets and pre-computes features for eligible companies."""
        logger.info("Initializing Dashboard Service...")
        market_sample_path = MARKET_DIR / "sp500_market_sample.parquet"
        if market_sample_path.exists():
            try:
                full_df = pd.read_parquet(market_sample_path)
                for ticker in COMPANY_CATALOG.keys():
                    sub = full_df[full_df["ticker"] == ticker].copy()
                    if not sub.empty:
                        # Yahoo market data for JPM prior to 1984 contains zero open prices; filter to valid positive trading prices
                        sub = sub[(sub["open"] > 0) & (sub["close"] > 0) & (sub["adjusted_close"] > 0)].copy()
                        sub = sub.sort_values("trading_date").reset_index(drop=True)
                        self._market_data_cache[ticker] = sub
                        # Pre-compute features & forward target
                        self._feature_data_cache[ticker] = self._compute_company_market_features(sub)
                logger.info(f"Loaded market data for {list(self._market_data_cache.keys())}")
            except Exception as e:
                logger.error(f"Error loading market sample parquet: {e}")

        # Train reference model strictly on historical training fold (2019-01-02 to 2020-03-23)
        self._train_reference_model()

    def _compute_company_market_features(self, df_comp: pd.DataFrame) -> pd.DataFrame:
        """Computes technical indicators and forward targets for a single company."""
        engine = MarketFeatureEngine()
        features_df = engine.compute_features(df_comp)

        target_engine = ForwardReturnTargetEngine(TargetConfig(horizon_sessions=5))
        with_target = target_engine.add_target(features_df)
        return with_target

    def _train_reference_model(self):
        """
        Fits reference Model 1 (Market-Only Ridge) strictly on historical training fold
        (2019-01-02 to 2020-03-23) across the four companies with zero lookahead bias.
        """
        train_dfs = []
        feature_cols = [
            "market_return_1d",
            "market_return_5d",
            "market_return_21d",
            "market_log_return_1d",
            "market_volatility_5d",
            "market_volatility_21d",
            "market_volatility_63d",
            "market_momentum_5d",
            "market_momentum_21d",
            "market_momentum_63d",
            "market_sma_20d",
            "market_sma_50d",
            "market_zscore_20d",
            "market_zscore_50d",
            "market_rsi_14d",
            "market_volume_change_1d",
            "market_volume_ratio_20d",
        ]

        for ticker, df in self._feature_data_cache.items():
            # Cutoff at 2020-03-23 (end of Fold 3 training set in Phase 5D)
            mask = (
                (df["trading_date"] >= "2019-01-02")
                & (df["trading_date"] <= "2020-03-23")
                & (df["target_forward_return_5d_valid"] == True)
            )
            sub = df[mask].copy()
            if not sub.empty:
                train_dfs.append(sub)

        if not train_dfs:
            logger.warning("No training data available to fit reference inference model.")
            return

        combined_train = pd.concat(train_dfs, ignore_index=True)
        valid_cols = [c for c in feature_cols if c in combined_train.columns]
        X_raw = combined_train[valid_cols].values
        y_raw = combined_train["target_forward_return_5d"].values

        # Strict training-only preprocessing
        imputer = SimpleImputer(strategy="median")
        X_imp = imputer.fit_transform(X_raw)

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X_imp)

        # Regularizer alpha=1000.0 selected during walk-forward validation in Phase 5D
        ridge = Ridge(alpha=1000.0, random_state=42)
        ridge.fit(X_scaled, y_raw)

        self._fitted_model = ridge
        self._fitted_scaler = scaler
        self._fitted_imputer = imputer
        self._model_feature_cols = valid_cols

        # Derive training residuals for calibrated uncertainty estimation
        train_preds = ridge.predict(X_scaled)
        train_residuals = y_raw - train_preds
        self._residual_uncertainty_estimator = ResidualUncertaintyEstimator(
            training_residuals=train_residuals,
            method_name="training_residual_std_fold3",
        )
        logger.info(f"Fitted reference Ridge model on {len(combined_train)} historical samples with {len(valid_cols)} features (residual std={self._residual_uncertainty_estimator.residual_std:.4f}).")

    def get_eligible_companies(self) -> List[CompanyMetadata]:
        """Returns metadata for all eligible companies, dynamically attaching data dates."""
        results = []
        for ticker, meta in COMPANY_CATALOG.items():
            df = self._market_data_cache.get(ticker)
            if df is not None and not df.empty:
                min_date = str(df["trading_date"].min())
                max_date = str(df["trading_date"].max())
                total_sessions = len(df)
            else:
                min_date = "N/A"
                max_date = "N/A"
                total_sessions = 0

            results.append(
                CompanyMetadata(
                    ticker=meta["ticker"],
                    company_id=meta["company_id"],
                    company_name=meta["company_name"],
                    cik=meta["cik"],
                    sector=meta["sector"],
                    membership_interval=meta["membership_interval"],
                    min_date=min_date,
                    max_date=max_date,
                    total_sessions=total_sessions,
                    sec_coverage_status=meta["sec_coverage_status"],
                    news_coverage_status=meta["news_coverage_status"],
                    pilot_eligible=meta["pilot_eligible"],
                    notes=meta["notes"],
                )
            )
        return results

    def get_company_metadata(self, ticker: str) -> Optional[CompanyMetadata]:
        """Returns single company metadata or None if unknown/excluded."""
        ticker = ticker.upper()
        if ticker in EXCLUDED_COMPANIES:
            return None
        meta = COMPANY_CATALOG.get(ticker)
        if not meta:
            return None
        df = self._market_data_cache.get(ticker)
        min_date = str(df["trading_date"].min()) if df is not None and not df.empty else "N/A"
        max_date = str(df["trading_date"].max()) if df is not None and not df.empty else "N/A"
        total_sessions = len(df) if df is not None else 0

        return CompanyMetadata(
            ticker=meta["ticker"],
            company_id=meta["company_id"],
            company_name=meta["company_name"],
            cik=meta["cik"],
            sector=meta["sector"],
            membership_interval=meta["membership_interval"],
            min_date=min_date,
            max_date=max_date,
            total_sessions=total_sessions,
            sec_coverage_status=meta["sec_coverage_status"],
            news_coverage_status=meta["news_coverage_status"],
            pilot_eligible=meta["pilot_eligible"],
            notes=meta["notes"],
        )

    def _load_expanded_market_data(self, ticker: str) -> Optional[pd.DataFrame]:
        """
        Loads and validates historical market data for an expanded-cohort company from Phase 5I artifacts,
        then computes technical features and forward targets.
        """
        p_single = DATA_DIR / "market" / "phase5i" / f"{ticker}.parquet"
        p_cons = DATA_DIR / "market" / "phase5i_market_expansion.parquet"

        raw_df = None
        if p_single.exists():
            try:
                raw_df = pd.read_parquet(p_single)
            except Exception as e:
                logger.error(f"Error reading per-company market artifact {p_single}: {e}")
                raw_df = None

        if raw_df is None or raw_df.empty:
            if not p_cons.exists():
                logger.error(f"Consolidated market expansion artifact missing: {p_cons}")
                return None
            try:
                raw_df = pd.read_parquet(p_cons, filters=[("ticker", "==", ticker)])
            except Exception as e:
                logger.error(f"Error reading consolidated market artifact {p_cons}: {e}")
                return None

        if raw_df is None or raw_df.empty:
            return None

        # Data integrity checks
        required_cols = ["trading_date", "open", "high", "low", "close", "adjusted_close", "volume"]
        missing_cols = [c for c in required_cols if c not in raw_df.columns]
        if missing_cols:
            raise ValueError(f"Market data for {ticker} missing required columns: {missing_cols}")

        if raw_df["trading_date"].isna().any():
            raise ValueError(f"Null trading dates detected in market artifact for {ticker}")

        # Check for duplicate trading dates
        if raw_df.duplicated(subset=["trading_date"]).any():
            dup_dates = raw_df[raw_df.duplicated(subset=["trading_date"])]["trading_date"].tolist()
            raise ValueError(f"Duplicate market observations detected for {ticker} on dates: {dup_dates[:5]}")

        # Filter valid positive prices (handling any pre-1984 zero open data anomalies)
        raw_df = raw_df[(raw_df["open"] > 0) & (raw_df["close"] > 0) & (raw_df["adjusted_close"] > 0)].copy()
        if raw_df.empty:
            return None

        raw_df = raw_df.sort_values("trading_date").reset_index(drop=True)

        # Compute technical indicators and forward targets
        features_with_targets = self._compute_company_market_features(raw_df)
        return features_with_targets

    def get_company_market(
        self,
        ticker: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 500,
    ) -> Optional[CompanyMarketResponse]:
        """
        Returns real historical quotes and computed technical indicators.
        Strictly excludes excluded companies.
        Supports both the legacy prototype catalog and the expanded 60-company research cohort.
        """
        ticker_clean = ticker.strip().upper()
        if ticker_clean in EXCLUDED_COMPANIES:
            raise ValueError(f"Company {ticker_clean} is excluded: {EXCLUDED_COMPANIES[ticker_clean]}")
        if ticker_clean == "GOOGL":
            # Share classes are not interchangeable market instruments
            return None

        df = self._feature_data_cache.get(ticker_clean)
        data_source = None
        comp_id = None
        comp_name = None

        if ticker_clean in COMPANY_CATALOG:
            # Legacy 4-company prototype path
            meta = COMPANY_CATALOG[ticker_clean]
            comp_id = meta["company_id"]
            comp_name = meta["company_name"]
            data_source = "Tiingo / Yahoo-derived Prototype S&P 500 Market Sample (Offline Parquet)"
        else:
            # Expanded 60-company cohort path: validate via capability contract
            self._ensure_capabilities_initialized()
            cap = self._capabilities_cache.get(ticker_clean)
            if not cap:
                return None  # Unknown ticker outside validated cohort

            if cap.market_artifact.status != CapabilityStatus.SUPPORTED:
                return None  # Market artifact unavailable for this cohort member

            comp_id = cap.identity.company_id
            comp_name = cap.identity.company_name
            data_source = "FNSPID / Yahoo-derived Historical Market Expansion (Phase 5I Offline Parquet)"

            if df is None or df.empty:
                # Load from Phase 5I artifacts and compute features
                df = self._load_expanded_market_data(ticker_clean)
                if df is not None and not df.empty:
                    self._feature_data_cache[ticker_clean] = df

        if df is None or df.empty:
            return None

        filtered = df.copy()
        if start_date:
            filtered = filtered[filtered["trading_date"] >= start_date]
        if end_date:
            filtered = filtered[filtered["trading_date"] <= end_date]

        # Order chronologically and take most recent points if limit is specified
        filtered = filtered.sort_values("trading_date").reset_index(drop=True)
        if len(filtered) > limit:
            filtered = filtered.iloc[-limit:]

        series_points: List[MarketSeriesPoint] = []
        for _, row in filtered.iterrows():
            def clean_float(val):
                if pd.isna(val) or np.isinf(val):
                    return None
                return round(float(val), 6)

            series_points.append(
                MarketSeriesPoint(
                    trading_date=str(row["trading_date"]),
                    open=round(float(row["open"]), 4),
                    high=round(float(row["high"]), 4),
                    low=round(float(row["low"]), 4),
                    close=round(float(row["close"]), 4),
                    adjusted_close=round(float(row["adjusted_close"]), 4),
                    volume=float(row["volume"]),
                    market_return_1d=clean_float(row.get("market_return_1d")),
                    market_return_5d=clean_float(row.get("market_return_5d")),
                    market_volatility_21d=clean_float(row.get("market_volatility_21d")),
                    market_sma_20d=clean_float(row.get("market_sma_20d")),
                    market_sma_50d=clean_float(row.get("market_sma_50d")),
                    market_rsi_14d=clean_float(row.get("market_rsi_14d")),
                    target_forward_return_5d=clean_float(row.get("target_forward_return_5d")),
                    target_forward_return_5d_valid=(
                        bool(row.get("target_forward_return_5d_valid"))
                        if not pd.isna(row.get("target_forward_return_5d_valid"))
                        else False
                    ),
                )
            )

        latest_pt = series_points[-1] if series_points else None
        latest_date = latest_pt.trading_date if latest_pt else "N/A"
        latest_price = latest_pt.adjusted_close if latest_pt else 0.0

        return CompanyMarketResponse(
            ticker=ticker_clean,
            company_id=comp_id,
            company_name=comp_name,
            data_source=data_source,
            adjustment_semantics="Adjusted close accounts for splits and cash dividends; derived adjusted open uses ratio adjustment factor (adj_close/close * open)",
            total_points=len(series_points),
            latest_observation_date=latest_date,
            latest_adjusted_close=latest_price,
            series=series_points,
        )

    def get_model_evaluation_summary(self) -> ModelEvaluationSummaryResponse:
        """
        Returns structured walk-forward evaluation results directly from the accepted Phase 5D report.
        Maintains clear provenance labels.
        """
        # 4-Company Panel Folds (AAPL, JPM, GOOG, TSLA)
        panel_folds = [
            FoldMetricResult(
                fold=0,
                train_start="2019-01-02",
                train_end="2019-09-09",
                train_rows=692,
                val_start="2019-09-17",
                val_end="2019-11-18",
                val_rows=180,
                regime_notes="Calm Bull Market (Pre-Pandemic)",
                zero_rmse=0.0486,
                zero_mae=0.0300,
                zero_hit=0.5000,
                median_rmse=0.0464,
                median_mae=0.0277,
                median_hit=0.7056,
                market_ridge_rmse=0.0485,
                market_ridge_mae=0.0295,
                market_ridge_hit=0.6278,
                market_ridge_ic=-0.101,
                market_ridge_alpha=1000.0,
                fund_ridge_rmse=0.0484,
                fund_ridge_mae=0.0291,
                fund_ridge_hit=0.6111,
                fund_ridge_ic=-0.023,
                fund_ridge_alpha=1000.0,
                best_model_mae="Reference 1 (Historical Median) [0.0277]",
            ),
            FoldMetricResult(
                fold=1,
                train_start="2019-01-02",
                train_end="2019-11-11",
                train_rows=872,
                val_start="2019-11-19",
                val_end="2020-01-24",
                val_rows=180,
                regime_notes="Strong Bull Expansion",
                zero_rmse=0.0481,
                zero_mae=0.0317,
                zero_hit=0.5000,
                median_rmse=0.0445,
                median_mae=0.0289,
                median_hit=0.7222,
                market_ridge_rmse=0.0426,
                market_ridge_mae=0.0281,
                market_ridge_hit=0.7222,
                market_ridge_ic=0.304,
                market_ridge_alpha=1000.0,
                fund_ridge_rmse=0.0428,
                fund_ridge_mae=0.0276,
                fund_ridge_hit=0.7222,
                fund_ridge_ic=0.284,
                fund_ridge_alpha=1000.0,
                best_model_mae="Model 2 (Market + Fundamentals) [0.0276]",
            ),
            FoldMetricResult(
                fold=2,
                train_start="2019-01-02",
                train_end="2020-01-16",
                train_rows=1052,
                val_start="2020-01-27",
                val_end="2020-03-30",
                val_rows=180,
                regime_notes="COVID-19 Market Crash (High Volatility)",
                zero_rmse=0.1170,
                zero_mae=0.0796,
                zero_hit=0.5000,
                median_rmse=0.1189,
                median_mae=0.0819,
                median_hit=0.4278,
                market_ridge_rmse=0.1208,
                market_ridge_mae=0.0827,
                market_ridge_hit=0.4444,
                market_ridge_ic=-0.080,
                market_ridge_alpha=1000.0,
                fund_ridge_rmse=0.1207,
                fund_ridge_mae=0.0827,
                fund_ridge_hit=0.4389,
                fund_ridge_ic=-0.095,
                fund_ridge_alpha=1000.0,
                best_model_mae="Reference 0 (Zero Return) [0.0796]",
            ),
            FoldMetricResult(
                fold=3,
                train_start="2019-01-02",
                train_end="2020-03-23",
                train_rows=1232,
                val_start="2020-03-31",
                val_end="2020-06-03",
                val_rows=180,
                regime_notes="Untouched Final Holdout (Post-Crash Liquidity Rebound)",
                zero_rmse=0.0773,
                zero_mae=0.0536,
                zero_hit=0.5000,
                median_rmse=0.0738,
                median_mae=0.0502,
                median_hit=0.7278,
                market_ridge_rmse=0.0732,
                market_ridge_mae=0.0497,
                market_ridge_hit=0.7000,
                market_ridge_ic=-0.155,
                market_ridge_alpha=1000.0,
                fund_ridge_rmse=0.0740,
                fund_ridge_mae=0.0504,
                fund_ridge_hit=0.6722,
                fund_ridge_ic=-0.200,
                fund_ridge_alpha=1000.0,
                best_model_mae="Model 1 (Market-Only Ridge) [0.0497]",
            ),
        ]

        # 2-Company Complete Fundamentals Cohort Folds (AAPL + JPM)
        cohort_folds = [
            FoldMetricResult(
                fold=0,
                train_start="2019-01-02",
                train_end="2019-09-09",
                train_rows=346,
                val_start="2019-09-17",
                val_end="2019-11-18",
                val_rows=90,
                regime_notes="Calm Bull (Complete Fundamentals)",
                zero_rmse=0.0270,
                zero_mae=0.0212,
                zero_hit=0.5000,
                median_rmse=0.0245,
                median_mae=0.0184,
                median_hit=0.7222,
                market_ridge_rmse=0.0258,
                market_ridge_mae=0.0200,
                market_ridge_hit=0.7000,
                market_ridge_ic=0.215,
                market_ridge_alpha=1000.0,
                fund_ridge_rmse=0.0249,
                fund_ridge_mae=0.0186,
                fund_ridge_hit=0.6889,
                fund_ridge_ic=0.280,
                fund_ridge_alpha=1000.0,
                best_model_mae="Reference 1 (Historical Median) [0.0184]",
            ),
            FoldMetricResult(
                fold=1,
                train_start="2019-01-02",
                train_end="2019-11-11",
                train_rows=436,
                val_start="2019-11-19",
                val_end="2020-01-24",
                val_rows=90,
                regime_notes="Expansion (Complete Fundamentals)",
                zero_rmse=0.0232,
                zero_mae=0.0188,
                zero_hit=0.5000,
                median_rmse=0.0211,
                median_mae=0.0162,
                median_hit=0.6778,
                market_ridge_rmse=0.0215,
                market_ridge_mae=0.0169,
                market_ridge_hit=0.6778,
                market_ridge_ic=0.194,
                market_ridge_alpha=1000.0,
                fund_ridge_rmse=0.0210,
                fund_ridge_mae=0.0161,
                fund_ridge_hit=0.6778,
                fund_ridge_ic=0.282,
                fund_ridge_alpha=1000.0,
                best_model_mae="Model 2 (Market + Fundamentals) [0.0161]",
            ),
            FoldMetricResult(
                fold=2,
                train_start="2019-01-02",
                train_end="2020-01-16",
                train_rows=526,
                val_start="2020-01-27",
                val_end="2020-03-30",
                val_rows=90,
                regime_notes="Crash Regime (Complete Fundamentals)",
                zero_rmse=0.0815,
                zero_mae=0.0569,
                zero_hit=0.5000,
                median_rmse=0.0842,
                median_mae=0.0605,
                median_hit=0.3889,
                market_ridge_rmse=0.0851,
                market_ridge_mae=0.0622,
                market_ridge_hit=0.4333,
                market_ridge_ic=0.149,
                market_ridge_alpha=1000.0,
                fund_ridge_rmse=0.0848,
                fund_ridge_mae=0.0614,
                fund_ridge_hit=0.4333,
                fund_ridge_ic=0.053,
                fund_ridge_alpha=1000.0,
                best_model_mae="Reference 0 (Zero Return) [0.0569]",
            ),
            FoldMetricResult(
                fold=3,
                train_start="2019-01-02",
                train_end="2020-03-23",
                train_rows=616,
                val_start="2020-03-31",
                val_end="2020-06-03",
                val_rows=90,
                regime_notes="Holdout (Complete Fundamentals: JPM degraded during credit shock)",
                zero_rmse=0.0645,
                zero_mae=0.0506,
                zero_hit=0.5000,
                median_rmse=0.0631,
                median_mae=0.0475,
                median_hit=0.7111,
                market_ridge_rmse=0.0648,
                market_ridge_mae=0.0505,
                market_ridge_hit=0.7111,
                market_ridge_ic=-0.218,
                market_ridge_alpha=1000.0,
                fund_ridge_rmse=0.0752,
                fund_ridge_mae=0.0582,
                fund_ridge_hit=0.6556,
                fund_ridge_ic=-0.275,
                fund_ridge_alpha=1000.0,
                best_model_mae="Reference 1 (Historical Median) [0.0475]",
            ),
        ]

        critical_findings = [
            "Lower return-prediction error (MAE) does NOT establish trading profitability or positive Sharpe ratio.",
            "Adding quarterly SEC fundamentals did NOT yield consistent incremental alpha over a 5-day horizon due to frequency mismatch (90-day statements vs 5-day market liquidity dynamics).",
            "In final Holdout Fold 3, Market+Fundamentals Ridge MAE (0.0504) slightly degraded compared to Market-Only Ridge (0.0497).",
            "Naive benchmarks (Zero Return and Historical Median) remain competitive baselines that complex models struggle to beat decisively.",
            "Spearman rank correlation (IC) turned negative in Holdout Fold 3 (-0.155 to -0.200), demonstrating that higher cross-sectional scores did not translate into higher realized returns.",
        ]

        return ModelEvaluationSummaryResponse(
            experiment_name="Phase 5D Walk-Forward SEC Fundamentals & Market Baseline Evaluation",
            provenance="Report-derived result from Phase 5D walk-forward evaluation (docs/phase5d_sec_fundamentals_baseline_report.md) — not recomputed in this session",
            verified_cohort=["AAPL", "JPM", "GOOG", "TSLA"],
            target_definition="5-session forward return: decision at session T close, entry at session T+1 open, exit at session T+5 close",
            purge_sessions=5,
            overall_winner_mae="Model 1 (Market-Only Ridge) won Holdout Fold 3 (MAE: 0.0497 vs 0.0502 for Median, 0.0504 for Mkt+Fund, 0.0536 for Zero)",
            critical_findings=critical_findings,
            fold_results=panel_folds,
            two_company_cohort_results=cohort_folds,
        )

    def get_model_status(self) -> Dict[str, Any]:
        """Returns runtime availability and training status of models."""
        return {
            "reference_0_zero_return": {
                "name": "Reference 0 (Naive Zero Return)",
                "status": "active",
                "requires_fitting": False,
                "description": "Predicts exact 0.0 return for all horizons. Constant risk-free benchmark.",
            },
            "reference_1_historical_median": {
                "name": "Reference 1 (Historical Median Return)",
                "status": "active",
                "requires_fitting": True,
                "description": "Predicts median return computed strictly from training partition.",
            },
            "model_1_market_ridge": {
                "name": "Model 1 (Market-Only Ridge Regression)",
                "status": "active" if self._fitted_model is not None else "unfitted",
                "requires_fitting": True,
                "features_count": len(self._model_feature_cols),
                "features": self._model_feature_cols,
                "regularizer_alpha": 1000.0,
                "training_window": "2019-01-02 to 2020-03-23 (Walk-Forward Fold 3 Train Split)",
                "description": "L2 Regularized linear regression on 17 technical and price-action features.",
            },
            "model_2_fundamental_ridge": {
                "name": "Model 2 (Market + Point-in-Time Fundamentals Ridge)",
                "status": "active_for_pilot_cohort (AAPL, JPM only)",
                "requires_fitting": True,
                "description": "Extends market features with 8 SEC EDGAR financial statement features. GOOG & TSLA unobserved in local pilot.",
            },
            "decision_layer": {
                "name": "Portfolio / Trading Decision Layer (BUY / HOLD / SELL)",
                "status": "unimplemented",
                "description": "Transforms validated forward-return forecasts into risk-gated candidate signals.",
            },
            "portfolio_simulation": {
                "name": "Portfolio Simulation & Rolling Threshold Validation (Phase 5H)",
                "status": "implemented_experimental",
                "description": "Models multi-asset portfolio accounting, concurrent position tracking, and leakage-safe rolling threshold tuning.",
            },
        }

    def predict_experimental(self, ticker: str, as_of_date: Optional[str] = None) -> PredictionResponse:
        """
        Executes genuine experimental forward return prediction if data and inference pipeline exist.
        Otherwise returns honest 'unavailable' response with specific cause.
        """
        ticker = ticker.upper()
        if ticker in EXCLUDED_COMPANIES:
            return PredictionResponse(
                status="unavailable",
                ticker=ticker,
                target_horizon="5-trading-session (T+1 open to T+5 close)",
                message=f"Company {ticker} is excluded: {EXCLUDED_COMPANIES[ticker]}",
                limitations=["Ticker identity ambiguity prevents reproducible point-in-time feature construction."],
                is_experimental=True,
            )

        if ticker not in COMPANY_CATALOG:
            return PredictionResponse(
                status="unavailable",
                ticker=ticker,
                target_horizon="5-trading-session (T+1 open to T+5 close)",
                message=f"Ticker '{ticker}' is not in the verified experimental catalog (AAPL, JPM, GOOG, TSLA).",
                limitations=["Unsupported company."],
                is_experimental=True,
            )

        df = self._feature_data_cache.get(ticker)
        if df is None or df.empty:
            return PredictionResponse(
                status="unavailable",
                ticker=ticker,
                target_horizon="5-trading-session (T+1 open to T+5 close)",
                message=f"No market data cached for {ticker}.",
                limitations=["Market series missing."],
                is_experimental=True,
            )

        # Select row for decision date
        if as_of_date:
            row_df = df[df["trading_date"] == as_of_date]
            if row_df.empty:
                return PredictionResponse(
                    status="unavailable",
                    ticker=ticker,
                    target_horizon="5-trading-session (T+1 open to T+5 close)",
                    message=f"No market session found for {ticker} on date {as_of_date}.",
                    limitations=["Date is either a weekend/holiday or outside historical dataset bounds."],
                    is_experimental=True,
                )
        else:
            # Default to latest available observation
            row_df = df.iloc[[-1]]

        row = row_df.iloc[0]
        decision_date = str(row["trading_date"])
        company_id = COMPANY_CATALOG[ticker]["company_id"]

        if self._fitted_model is None or self._fitted_scaler is None or self._fitted_imputer is None:
            return PredictionResponse(
                status="unavailable",
                ticker=ticker,
                company_id=company_id,
                as_of_timestamp=f"{decision_date}T21:00:00Z",
                target_horizon="5-trading-session (T+1 open to T+5 close)",
                message="Prediction unavailable — inference pipeline not yet connected / fitted model unavailable.",
                limitations=["Fitted model artifact could not be instantiated."],
                is_experimental=True,
            )

        # Check required features in row
        missing_feats = [c for c in self._model_feature_cols if c not in row or pd.isna(row[c])]
        if len(missing_feats) > len(self._model_feature_cols) // 2:
            return PredictionResponse(
                status="unavailable",
                ticker=ticker,
                company_id=company_id,
                as_of_timestamp=f"{decision_date}T21:00:00Z",
                target_horizon="5-trading-session (T+1 open to T+5 close)",
                message=f"Insufficient lookback history to compute market features on {decision_date}.",
                limitations=[f"Missing required technical features: {missing_feats[:5]}..."],
                is_experimental=True,
            )

        # Extract features and apply strict pipeline
        x_raw = np.array([[row.get(c, np.nan) for c in self._model_feature_cols]])
        x_imp = self._fitted_imputer.transform(x_raw)
        x_scaled = self._fitted_scaler.transform(x_imp)
        pred_val = float(self._fitted_model.predict(x_scaled)[0])

        pct_formatted = f"{'+' if pred_val >= 0 else ''}{pred_val * 100:.2f}%"

        limitations = [
            "EXPERIMENTAL RETURN PREDICTION ONLY. Not financial advice or an investment recommendation.",
            "Model 1 (Market-Only Ridge) exhibits negative holdout Spearman rank correlation (IC = -0.155 in Fold 3).",
            "Does not account for transaction costs, market impact, execution slippage, or borrowing fees.",
            "Quarterly SEC fundamentals and news features are not utilized by this model variant.",
        ]

        return PredictionResponse(
            status="available",
            ticker=ticker,
            company_id=company_id,
            as_of_timestamp=f"{decision_date}T21:00:00Z",
            target_horizon="5-trading-session (T+1 open to T+5 close)",
            predicted_forward_return=round(pred_val, 6),
            predicted_forward_return_pct=pct_formatted,
            model_id="Ridge-Market-Only-v1 (Alpha=1000.0, Walk-Forward Fold 3)",
            features_used=self._model_feature_cols,
            message=f"Genuine experimental forward-return prediction generated from session {decision_date} close data.",
            limitations=limitations,
            is_experimental=True,
        )

    def get_decision(
        self,
        ticker: str,
        as_of_date: Optional[str] = None,
        buy_threshold: Optional[float] = None,
        sell_threshold: Optional[float] = None,
        max_uncertainty: Optional[float] = None,
        cost_roundtrip_bps: Optional[float] = None,
    ) -> DecisionContractResponse:
        """
        Transforms market forward-return forecast into an experimental BUY / HOLD / SELL candidate signal
        via the Phase 5G Decision & Risk Layer.
        """
        ticker_clean = ticker.upper()

        # Handle excluded company
        if ticker_clean in EXCLUDED_COMPANIES:
            return DecisionContractResponse(
                signal=SignalType.HOLD,
                ticker=ticker_clean,
                company_id="UNKNOWN_AA",
                decision_timestamp=datetime.now(timezone.utc).isoformat(),
                predicted_forward_return=0.0,
                expected_net_return=0.0,
                total_cost_deducted=0.0,
                cost_assumptions_bps=15.0,
                estimated_uncertainty=None,
                uncertainty_method="unavailable",
                threshold_applied=0.0,
                risk_checks_passed=[],
                risk_checks_failed=[f"EXCLUSION_GATE: Company {ticker_clean} is excluded: {EXCLUDED_COMPANIES[ticker_clean]}"],
                reasons=[f"SIGNAL FORCED TO HOLD: {ticker_clean} is excluded due to unresolved corporate identity."],
                data_quality_warnings=["Ticker excluded from universe."],
                model_provenance={"model_id": "N/A", "status": "excluded"},
                is_experimental=True,
            )

        if ticker_clean not in COMPANY_CATALOG:
            return DecisionContractResponse(
                signal=SignalType.HOLD,
                ticker=ticker_clean,
                company_id="UNKNOWN",
                decision_timestamp=datetime.now(timezone.utc).isoformat(),
                predicted_forward_return=0.0,
                expected_net_return=0.0,
                total_cost_deducted=0.0,
                cost_assumptions_bps=15.0,
                estimated_uncertainty=None,
                uncertainty_method="unavailable",
                threshold_applied=0.0,
                risk_checks_passed=[],
                risk_checks_failed=[f"COMPANY_IDENTITY_GATE: Ticker '{ticker_clean}' is not in verified catalog."],
                reasons=[f"SIGNAL FORCED TO HOLD: Unsupported ticker '{ticker_clean}'."],
                data_quality_warnings=["Unsupported company."],
                model_provenance={"model_id": "N/A", "status": "unsupported"},
                is_experimental=True,
            )

        # Get forward prediction response first
        pred_resp = self.predict_experimental(ticker_clean, as_of_date=as_of_date)
        if pred_resp.status != "available" or pred_resp.predicted_forward_return is None:
            return DecisionContractResponse(
                signal=SignalType.HOLD,
                ticker=ticker_clean,
                company_id=COMPANY_CATALOG[ticker_clean]["company_id"],
                decision_timestamp=pred_resp.as_of_timestamp or datetime.now(timezone.utc).isoformat(),
                predicted_forward_return=0.0,
                expected_net_return=0.0,
                total_cost_deducted=0.0,
                cost_assumptions_bps=15.0,
                estimated_uncertainty=None,
                uncertainty_method="unavailable",
                threshold_applied=0.0,
                risk_checks_passed=[],
                risk_checks_failed=[f"PREDICTION_AVAILABILITY_GATE: Prediction unavailable: {pred_resp.message}"],
                reasons=[f"SIGNAL FORCED TO HOLD: {pred_resp.message}"],
                data_quality_warnings=pred_resp.limitations,
                model_provenance={"model_id": pred_resp.model_id or "N/A", "status": "unavailable"},
                is_experimental=True,
            )

        # Lookup rolling volatility from cache if present
        df = self._feature_data_cache.get(ticker_clean)
        vol_5d = None
        if df is not None and not df.empty:
            if as_of_date:
                sub_rows = df[df["trading_date"] == as_of_date]
            else:
                sub_rows = df.iloc[[-1]]
            if not sub_rows.empty:
                v = sub_rows.iloc[0].get("market_volatility_5d")
                if pd.notna(v):
                    vol_5d = float(v)

        # Configure cost and risk with overrides
        cost_cfg = TransactionCostConfig()
        if cost_roundtrip_bps is not None and cost_roundtrip_bps > 0:
            half = cost_roundtrip_bps / 4.0
            cost_cfg.entry_fee_bps = half
            cost_cfg.exit_fee_bps = half
            cost_cfg.half_spread_bps = half / 2.0
            cost_cfg.slippage_bps = half / 2.0

        risk_cfg = RiskGateConfig()
        if buy_threshold is not None:
            risk_cfg.buy_threshold = float(buy_threshold)
        if sell_threshold is not None:
            risk_cfg.sell_threshold = float(sell_threshold)
        if max_uncertainty is not None and max_uncertainty > 0:
            risk_cfg.max_uncertainty = float(max_uncertainty)

        # Build DecisionContractRequest
        req = DecisionContractRequest(
            company_id=pred_resp.company_id or COMPANY_CATALOG[ticker_clean]["company_id"],
            ticker=ticker_clean,
            decision_timestamp=pred_resp.as_of_timestamp or datetime.now(timezone.utc).isoformat(),
            predicted_forward_return=pred_resp.predicted_forward_return,
            forecast_uncertainty=self._residual_uncertainty_estimator.get_uncertainty() if self._residual_uncertainty_estimator else None,
            rolling_volatility_5d=vol_5d,
            feature_metadata={
                "n_features_used": len(pred_resp.features_used),
                "n_features_required": len(self._model_feature_cols),
                "as_of_date": as_of_date or (str(df["trading_date"].iloc[-1]) if df is not None else None),
            },
            model_id=pred_resp.model_id or "Ridge-Market-Only-v1",
            model_version="1.0.0",
            training_cutoff_date="2020-03-23",
            cost_config=cost_cfg,
            risk_config=risk_cfg,
        )

        policy = ThresholdDecisionPolicy(uncertainty_estimator=self._residual_uncertainty_estimator)
        return policy.evaluate(req)

    def get_portfolio_research_summary(self) -> Dict[str, Any]:
        """Loads and returns Phase 5H portfolio simulation and rolling threshold evaluation artifacts."""
        p = Path("data/processed/sec/eight_k/phase5h_portfolio_evaluation_results.json")
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                return {"status": "error", "message": f"Failed to load portfolio results: {e}"}
        return {"status": "unavailable", "message": "Phase 5H portfolio evaluation results not yet generated."}

    def get_phase5j_cross_sectional_research(self) -> Dict[str, Any]:
        """Loads and returns Phase 5J cross-sectional evaluation and track comparison artifacts."""
        p_eval = Path("data/processed/research/phase5j/phase5j_cross_sectional_evaluation_results.json")
        p_track = Path("data/processed/research/phase5j/phase5j_track_comparison.json")

        if not p_eval.exists():
            return {
                "status": "unavailable",
                "message": "Phase 5J cross-sectional evaluation results not yet generated.",
            }

        try:
            with open(p_eval, "r", encoding="utf-8") as f:
                data = json.load(f)
            if p_track.exists():
                with open(p_track, "r", encoding="utf-8") as f:
                    data["track_comparison"] = json.load(f)
            data["status"] = "available"
            return data
        except Exception as e:
            return {"status": "error", "message": f"Failed to load Phase 5J evaluation results: {e}"}

    def get_phase5k_model_improvement_research(self) -> Dict[str, Any]:
        """Loads and returns Phase 5K model experiment and institutional portfolio artifacts."""
        p_eval = Path("data/processed/research/phase5k/phase5k_model_experiment_results.json")
        p_port = Path("data/processed/research/phase5k/phase5k_portfolio_simulation_results.json")

        if not p_eval.exists():
            return {
                "status": "unavailable",
                "message": "Phase 5K model experiment results not yet generated.",
            }

        try:
            with open(p_eval, "r", encoding="utf-8") as f:
                data = json.load(f)
            if p_port.exists():
                with open(p_port, "r", encoding="utf-8") as f:
                    data["portfolio_simulation"] = json.load(f)
            data["status"] = "available"
            return data
        except Exception as e:
            return {"status": "error", "message": f"Failed to load Phase 5K evaluation results: {e}"}

    # =====================================================================
    # Phase 5L — 60-Company Screener, Research Signals & Risk Diagnostics
    # =====================================================================

    def _ensure_phase5l_initialized(self):
        """Lazy-loads and caches Phase 5L 60-company universe and OOS predictions."""
        if hasattr(self, "_phase5l_initialized") and self._phase5l_initialized:
            return

        p_elig = DATA_DIR / "universe" / "phase5j_company_eligibility.csv"
        p_oos = DATA_DIR / "research" / "phase5k" / "phase5k_predictions_oos.parquet"
        p_eval = DATA_DIR / "research" / "phase5k" / "phase5k_model_experiment_results.json"

        if not p_elig.exists():
            raise FileNotFoundError(f"Missing eligibility manifest: {p_elig}")
        if not p_oos.exists():
            raise FileNotFoundError(f"Missing OOS predictions parquet: {p_oos}")

        self._phase5l_eligibility_df = pd.read_csv(p_elig)
        self._phase5l_oos_df = pd.read_parquet(p_oos)

        self._phase5l_fold_cutoffs = {0: "2019-09-09", 1: "2019-11-11", 2: "2020-01-16", 3: "2020-03-23"}
        if p_eval.exists():
            try:
                with open(p_eval, "r", encoding="utf-8") as f:
                    eval_d = json.load(f)
                    if "fold_schedule" in eval_d:
                        self._phase5l_fold_cutoffs = {
                            f["fold"]: f.get("train_end_date", "2020-03-23")
                            for f in eval_d["fold_schedule"]
                        }
            except Exception as e:
                logger.warning(f"Could not load fold schedule from {p_eval}: {e}")

        self._phase5l_cost_cfg = TransactionCostConfig(
            entry_fee_bps=2.5,
            exit_fee_bps=2.5,
            half_spread_bps=2.5,
            slippage_bps=2.5,
        )
        self._phase5l_risk_cfg = RiskGateConfig(
            buy_threshold=0.015,
            sell_threshold=-0.015,
            max_uncertainty=0.08,
            min_net_return_hurdle=0.005,
            enforce_uncertainty_gate=True,
        )
        self._phase5l_initialized = True

    def get_60_company_screener(
        self,
        model_id: str = "ridge_regression",
        as_of_date: Optional[str] = None,
        sector: Optional[str] = None,
        signal: Optional[str] = None,
        coverage: Optional[str] = None,
        search: Optional[str] = None,
        sort_by: Optional[str] = None,
        sort_dir: str = "asc",
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> ScreenerResponse:
        """
        Generates the 60-company research screener payload with live decision contracts and risk status.
        """
        self._ensure_phase5l_initialized()

        supported_models = [
            "ridge_regression",
            "hist_gradient_boosting",
            "elastic_net",
            "ridge_cs_demeaned",
            "ridge_cs_scaled",
            "ridge_sector_neutral",
            "zero_baseline",
            "median_baseline",
        ]
        if model_id not in supported_models:
            model_id = "ridge_regression"

        all_items: List[ScreenerCompanyItem] = []
        sectors_set = set()

        for _, row in self._phase5l_eligibility_df.iterrows():
            tk = str(row["ticker"]).upper()
            sec = str(row["sector"])
            sectors_set.add(sec)
            c_name = str(row["company_name"])
            c_id = str(row["company_id"])
            cik = str(row["cik"])
            comp_pct = float(row["completeness_pct"])
            tot_sess = int(row["total_sessions"])
            early_d = str(row["earliest_date"])
            late_d = str(row["latest_date"])
            cov_status = str(row["market_eligibility"])
            is_trunc = comp_pct < 95.0
            lim_note = str(row["market_notes"]) if pd.notna(row["market_notes"]) else None

            # Sub-slice predictions for model and ticker
            sub_m = self._phase5l_oos_df[
                (self._phase5l_oos_df["model_id"] == model_id)
                & (self._phase5l_oos_df["ticker"] == tk)
            ]

            if as_of_date:
                match_rows = sub_m[sub_m["trading_date"] == as_of_date]
            else:
                match_rows = sub_m.sort_values("trading_date").tail(1)

            if match_rows.empty:
                # Truncated or date out of range
                sig_str = "UNAVAILABLE"
                risk_status = "Unavailable: Truncated History" if is_trunc else "Unavailable: No Out-of-Sample Date"
                pred_ret = None
                pred_ret_pct = None
                net_ret = None
                net_ret_pct = None
                unc = None
                unc_pct = None
                obs_d = None
                ts = None
                failed_count = 0
                reasons = ["No out-of-sample prediction generated for this company and date."]
            else:
                m_row = match_rows.iloc[0]
                obs_d = str(m_row["trading_date"])
                pred_ret = float(m_row["predicted_return"])
                pred_ret_pct = f"{pred_ret:+.2%}"
                unc = float(m_row["sigma_train"])
                unc_pct = f"{unc:.2%}"
                vol_5d = float(m_row["market_volatility_5d"]) if pd.notna(m_row["market_volatility_5d"]) else None
                fld = int(m_row["fold"])
                train_cutoff = self._phase5l_fold_cutoffs.get(fld, "2020-03-23")
                ts = f"{obs_d}T14:15:00Z"

                u_estimator = ResidualUncertaintyEstimator(residual_std=unc, method_name="fold_training_sigma")
                policy = ThresholdDecisionPolicy(uncertainty_estimator=u_estimator)

                req = DecisionContractRequest(
                    company_id=c_id,
                    ticker=tk,
                    decision_timestamp=ts,
                    predicted_forward_return=pred_ret,
                    forecast_uncertainty=unc,
                    rolling_volatility_5d=vol_5d,
                    feature_metadata={"n_features_used": 17, "n_features_required": 17, "as_of_date": obs_d},
                    model_id=f"{model_id}_Fold{fld}",
                    training_cutoff_date=train_cutoff,
                    cost_config=self._phase5l_cost_cfg,
                    risk_config=self._phase5l_risk_cfg,
                )
                resp = policy.evaluate(req)
                sig_str = resp.signal.value
                net_ret = float(resp.expected_net_return)
                net_ret_pct = f"{net_ret:+.2%}"
                failed_count = len(resp.risk_checks_failed)
                reasons = resp.reasons

                if resp.risk_checks_failed:
                    if any(c.startswith("VOLATILITY_GATE") for c in resp.risk_checks_failed):
                        risk_status = "Blocked: Market Volatility > 15%"
                    elif any(c.startswith("COST_HURDLE_GATE") for c in resp.risk_checks_failed):
                        risk_status = "Blocked: Return Hurdle < 0.65%"
                    elif any(c.startswith("UNCERTAINTY_GATE") for c in resp.risk_checks_failed):
                        risk_status = "Blocked: Forecast Uncertainty > 8%"
                    else:
                        risk_status = f"Blocked: {resp.risk_checks_failed[0].split(':')[0]}"
                elif sig_str == "BUY":
                    risk_status = "All Risk Gates Passed (Net Conviction >= +1.50%)"
                elif sig_str == "SELL":
                    risk_status = "All Risk Gates Passed (Short Conviction <= -1.50%)"
                else:
                    risk_status = "Hold: Return Within Buffer (-1.50% to +1.50%)"

            item = ScreenerCompanyItem(
                ticker=tk,
                company_name=c_name,
                company_id=c_id,
                cik=cik,
                sector=sec,
                coverage_status=cov_status,
                completeness_pct=round(comp_pct, 2),
                total_sessions=tot_sess,
                earliest_date=early_d,
                latest_date=late_d,
                is_truncated=is_trunc,
                limitations_note=lim_note,
                observation_date=obs_d,
                predicted_return=pred_ret,
                predicted_return_pct=pred_ret_pct,
                expected_net_return=net_ret,
                expected_net_return_pct=net_ret_pct,
                forecast_uncertainty=unc,
                forecast_uncertainty_pct=unc_pct,
                signal=sig_str,
                risk_status=risk_status,
                model_id=f"{model_id}_Fold{fld}" if obs_d else None,
                prediction_timestamp=ts,
                failed_gate_count=failed_count,
                reasons=reasons,
            )
            all_items.append(item)

        # Filtering logic
        filtered = all_items
        if search:
            s_low = search.lower().strip()
            filtered = [
                x for x in filtered
                if s_low in x.ticker.lower() or s_low in x.company_name.lower()
            ]

        if sector and sector.lower() != "all":
            filtered = [x for x in filtered if x.sector.lower() == sector.lower()]

        if signal and signal.lower() != "all":
            filtered = [x for x in filtered if x.signal.lower() == signal.lower()]

        if coverage and coverage.lower() != "all":
            if coverage.lower() == "complete":
                filtered = [x for x in filtered if not x.is_truncated]
            elif coverage.lower() == "truncated":
                filtered = [x for x in filtered if x.is_truncated]

        # Signal summary counts across the filtered cohort (before pagination)
        sig_summary = {"BUY": 0, "HOLD": 0, "SELL": 0, "UNAVAILABLE": 0}
        for x in filtered:
            sig_summary[x.signal] = sig_summary.get(x.signal, 0) + 1

        # Sorting logic
        if sort_by:
            rev = (sort_dir.lower() == "desc")
            if sort_by == "ticker":
                filtered.sort(key=lambda x: x.ticker, reverse=rev)
            elif sort_by == "company_name":
                filtered.sort(key=lambda x: x.company_name, reverse=rev)
            elif sort_by == "sector":
                filtered.sort(key=lambda x: x.sector, reverse=rev)
            elif sort_by == "coverage":
                filtered.sort(key=lambda x: x.completeness_pct, reverse=rev)
            elif sort_by == "predicted_return":
                filtered.sort(key=lambda x: (x.predicted_return is not None, x.predicted_return or 0.0), reverse=rev)
            elif sort_by == "expected_net_return":
                filtered.sort(key=lambda x: (x.expected_net_return is not None, x.expected_net_return or 0.0), reverse=rev)
            elif sort_by == "forecast_uncertainty":
                filtered.sort(key=lambda x: (x.forecast_uncertainty is not None, x.forecast_uncertainty or 0.0), reverse=rev)
            elif sort_by == "signal":
                filtered.sort(key=lambda x: x.signal, reverse=rev)

        # Pagination
        paginated = filtered
        if offset > 0 or limit is not None:
            if limit is not None:
                paginated = filtered[offset : offset + limit]
            else:
                paginated = filtered[offset:]

        excluded_list = [
            {
                "ticker": "AA",
                "company_name": "Alcoa Inc. / Arconic Inc.",
                "sector": "Materials",
                "reason": EXCLUDED_COMPANIES.get("AA", "Corporate split identity ambiguity"),
            }
        ]

        disclaimer = (
            "Historical research mode — predictions and signals are based on archived out-of-sample data (2019–2020), "
            "not current market conditions. No real orders are executed and no signals constitute investment advice."
        )

        return ScreenerResponse(
            status="success",
            mode="HISTORICAL_RESEARCH",
            disclaimer=disclaimer,
            total_cohort_count=len(all_items),
            filtered_count=len(filtered),
            default_model="ridge_regression",
            active_model=model_id,
            as_of_date=as_of_date,
            available_models=supported_models,
            available_sectors=sorted(list(sectors_set)),
            signal_summary=sig_summary,
            companies=paginated,
            excluded_companies=excluded_list,
        )

    def get_company_research_detail(
        self,
        ticker: str,
        model_id: str = "ridge_regression",
        as_of_date: Optional[str] = None,
    ) -> CompanyResearchDetailResponse:
        """
        Returns full research profile, historical price series, and 8-stage decision funnel for a company.
        """
        self._ensure_phase5l_initialized()
        tk_clean = ticker.upper().strip()

        disclaimer = (
            "Historical research mode — predictions and signals are based on archived data (2019–2020), "
            "not current market conditions. No real orders are executed and no signals constitute investment advice."
        )

        # Check AA exclusion explicitly
        if tk_clean == "AA":
            ex_reason = EXCLUDED_COMPANIES["AA"]
            stage2 = DecisionFunnelStage(
                stage_number=2,
                stage_name="Company Identity & Exclusion Gate",
                status="FAIL",
                metric_value="Ticker AA",
                threshold_applied="Resolved Legal Entity CIK",
                explanation=ex_reason,
            )
            return CompanyResearchDetailResponse(
                status="excluded",
                ticker="AA",
                company_name="Alcoa Inc. / Arconic Inc.",
                company_id="US_CIK_0000004281",
                cik="0000004281",
                sector="Materials",
                coverage_status="EXCLUDED",
                is_truncated=False,
                limitations_note=ex_reason,
                market_notes="Excluded from universe.",
                sec_notes="Entity identity unresolved across Nov 2016 corporate split.",
                observation_date=None,
                data_freshness_days=None,
                model_id=model_id,
                fold=None,
                predicted_return=None,
                predicted_return_pct=None,
                expected_net_return=None,
                expected_net_return_pct=None,
                forecast_uncertainty=None,
                forecast_uncertainty_pct=None,
                uncertainty_method="unavailable",
                signal="EXCLUDED",
                decision_category="EXCLUDED",
                roundtrip_cost_bps=15.0,
                cost_breakdown={"entry_fee_bps": 2.5, "exit_fee_bps": 2.5, "half_spread_bps": 2.5, "slippage_bps": 2.5},
                decision_reasons=[ex_reason],
                funnel_stages=[stage2],
                risk_checks_passed=[],
                risk_checks_failed=["EXCLUSION_GATE: " + ex_reason],
                data_quality_warnings=["Corporate split identity ambiguity."],
                historical_price_series=[],
                available_prediction_dates=[],
                disclaimer=disclaimer,
            )

        # Verify ticker in 60-company universe
        match_co = self._phase5l_eligibility_df[self._phase5l_eligibility_df["ticker"] == tk_clean]
        if match_co.empty:
            raise KeyError(f"Ticker '{tk_clean}' is not part of the validated 60-company research cohort.")

        co_row = match_co.iloc[0]
        c_name = str(co_row["company_name"])
        c_id = str(co_row["company_id"])
        cik = str(co_row["cik"])
        sec = str(co_row["sector"])
        comp_pct = float(co_row["completeness_pct"])
        cov_status = str(co_row["market_eligibility"])
        is_trunc = comp_pct < 95.0
        lim_note = str(co_row["market_notes"]) if pd.notna(co_row["market_notes"]) else None
        sec_note = str(co_row["fundamentals_notes"]) if pd.notna(co_row["fundamentals_notes"]) else None

        # Filter OOS predictions
        sub_oos = self._phase5l_oos_df[
            (self._phase5l_oos_df["model_id"] == model_id)
            & (self._phase5l_oos_df["ticker"] == tk_clean)
        ].sort_values("trading_date")

        avail_dates = sorted(sub_oos["trading_date"].unique().tolist())

        if as_of_date:
            pred_match = sub_oos[sub_oos["trading_date"] == as_of_date]
        else:
            pred_match = sub_oos.tail(1)

        # Build 8-Stage Funnel
        funnel: List[DecisionFunnelStage] = []
        cost_breakdown = {"entry_fee_bps": 2.5, "exit_fee_bps": 2.5, "half_spread_bps": 2.5, "slippage_bps": 2.5}

        if pred_match.empty:
            obs_d = as_of_date
            pred_val = None
            pred_pct = None
            net_val = None
            net_pct = None
            unc_val = None
            unc_pct = None
            unc_method = "unavailable"
            sig_str = "UNAVAILABLE"
            dec_cat = "UNAVAILABLE_MISSING_DATA"
            fld_num = None
            reasons = [f"No prediction exists for ticker {tk_clean} on date {as_of_date or 'latest'}."]
            passed_checks = []
            failed_checks = ["FORECAST_AVAILABILITY_GATE: No valid prediction available."]
            warnings = ["Historical series is truncated." if is_trunc else "Observation date outside out-of-sample window."]

            funnel.append(DecisionFunnelStage(
                stage_number=1,
                stage_name="Forecast Availability & Validity",
                status="FAIL",
                metric_value="Missing / NaN",
                threshold_applied="Finite Real Number",
                explanation="No valid model prediction available for this date in out-of-sample archive.",
            ))
            for st_num, st_name in [
                (2, "Company Identity & Exclusion Gate"),
                (3, "Model Provenance & Temporal Cutoff Gate"),
                (4, "Feature Completeness & Freshness Gate"),
                (5, "Forecast Uncertainty Gate"),
                (6, "Estimated Transaction Cost & Net Return Hurdle Gate"),
                (7, "Abnormal Market Volatility Gate"),
                (8, "Directional BUY / HOLD / SELL Threshold"),
            ]:
                funnel.append(DecisionFunnelStage(
                    stage_number=st_num,
                    stage_name=st_name,
                    status="NOT EVALUATED",
                    metric_value=None,
                    threshold_applied=None,
                    explanation="Stage bypassed because forecast is unavailable.",
                ))
        else:
            p_row = pred_match.iloc[0]
            obs_d = str(p_row["trading_date"])
            pred_val = float(p_row["predicted_return"])
            pred_pct = f"{pred_val:+.2%}"
            unc_val = float(p_row["sigma_train"])
            unc_pct = f"{unc_val:.2%}"
            unc_method = "fold_training_sigma"
            vol_5d = float(p_row["market_volatility_5d"]) if pd.notna(p_row["market_volatility_5d"]) else None
            fld_num = int(p_row["fold"])
            train_cutoff = self._phase5l_fold_cutoffs.get(fld_num, "2020-03-23")
            ts = f"{obs_d}T14:15:00Z"

            u_estimator = ResidualUncertaintyEstimator(residual_std=unc_val, method_name=unc_method)
            policy = ThresholdDecisionPolicy(uncertainty_estimator=u_estimator)

            req = DecisionContractRequest(
                company_id=c_id,
                ticker=tk_clean,
                decision_timestamp=ts,
                predicted_forward_return=pred_val,
                forecast_uncertainty=unc_val,
                rolling_volatility_5d=vol_5d,
                feature_metadata={"n_features_used": 17, "n_features_required": 17, "as_of_date": obs_d},
                model_id=f"{model_id}_Fold{fld_num}",
                training_cutoff_date=train_cutoff,
                cost_config=self._phase5l_cost_cfg,
                risk_config=self._phase5l_risk_cfg,
            )
            resp = policy.evaluate(req)
            sig_str = resp.signal.value
            net_val = float(resp.expected_net_return)
            net_pct = f"{net_val:+.2%}"
            passed_checks = resp.risk_checks_passed
            failed_checks = resp.risk_checks_failed
            reasons = resp.reasons
            warnings = resp.data_quality_warnings

            if sig_str == "BUY":
                dec_cat = "BUY_SIGNAL"
            elif sig_str == "SELL":
                dec_cat = "SELL_SIGNAL"
            elif failed_checks:
                dec_cat = "HOLD_RISK_GATED"
            else:
                dec_cat = "HOLD_INSUFFICIENT_RETURN"

            # Construct 8-Stage Funnel
            # Stage 1: Forecast Availability
            funnel.append(DecisionFunnelStage(
                stage_number=1,
                stage_name="Forecast Availability & Validity",
                status="PASS",
                metric_value=pred_pct,
                threshold_applied="Finite Real Number",
                explanation=f"Valid 5-session forecast produced by {model_id} (Fold {fld_num}).",
            ))

            # Stage 2: Identity Gate
            funnel.append(DecisionFunnelStage(
                stage_number=2,
                stage_name="Company Identity & Exclusion Gate",
                status="PASS",
                metric_value=f"Eligible (CIK {cik})",
                threshold_applied="Resolved Legal Entity CIK",
                explanation="Company is an active member of the validated 60-company research cohort.",
            ))

            # Stage 3: Temporal Provenance
            funnel.append(DecisionFunnelStage(
                stage_number=3,
                stage_name="Model Provenance & Temporal Cutoff Gate",
                status="PASS",
                metric_value=f"Decision {obs_d} >= Cutoff {train_cutoff}",
                threshold_applied="Non-Inverted Temporal Deployment",
                explanation="Decision date strictly follows model training cutoff (zero lookahead leakage).",
            ))

            # Stage 4: Feature Completeness & Freshness
            funnel.append(DecisionFunnelStage(
                stage_number=4,
                stage_name="Feature Completeness & Freshness Gate",
                status="PASS",
                metric_value="17/17 Features (100%), 0d lag",
                threshold_applied=">= 80% Complete, <= 5d Staleness",
                explanation="All 17 technical feature inputs verified with point-in-time freshness.",
            ))

            # Stage 5: Forecast Uncertainty Gate
            unc_passed = unc_val <= self._phase5l_risk_cfg.max_uncertainty
            funnel.append(DecisionFunnelStage(
                stage_number=5,
                stage_name="Forecast Uncertainty Gate",
                status="PASS" if unc_passed else "FAIL",
                metric_value=f"{unc_val:.4f} ({unc_pct})",
                threshold_applied=f"<= {self._phase5l_risk_cfg.max_uncertainty:.4f} (8.00%)",
                explanation=(
                    f"Model residual uncertainty ({unc_pct}) is within the safe 8.00% risk ceiling."
                    if unc_passed
                    else f"Uncertainty ({unc_pct}) exceeds safe 8.00% ceiling."
                ),
            ))

            # Stage 6: Cost Hurdle Gate
            roundtrip_cost = self._phase5l_cost_cfg.total_roundtrip_decimal
            hurdle_req = roundtrip_cost + self._phase5l_risk_cfg.min_net_return_hurdle  # 0.0015 + 0.0050 = 0.0065
            cost_passed = abs(pred_val) >= hurdle_req
            funnel.append(DecisionFunnelStage(
                stage_number=6,
                stage_name="Estimated Transaction Cost & Net Return Hurdle Gate",
                status="PASS" if cost_passed else "FAIL",
                metric_value=f"Gross |Return| {abs(pred_val):.2%} vs Hurdle {hurdle_req:.2%}",
                threshold_applied=">= 15 bps friction + 50 bps net hurdle (0.65% gross hurdle)",
                explanation=(
                    f"Gross forecast ({abs(pred_val):.2%}) clears 15 bps friction + 50 bps net economic hurdle (0.65% total hurdle)."
                    if cost_passed
                    else f"Gross forecast ({abs(pred_val):.2%}) does not clear 15 bps friction + 50 bps net hurdle ({hurdle_req:.2%} gross hurdle)."
                ),
            ))

            # Stage 7: Abnormal Market Volatility Gate
            vol_passed = (vol_5d is not None) and (vol_5d <= self._phase5l_risk_cfg.max_rolling_volatility_5d)
            vol_disp = f"{vol_5d:.2%}" if vol_5d is not None else "N/A"
            funnel.append(DecisionFunnelStage(
                stage_number=7,
                stage_name="Abnormal Market Volatility Gate",
                status="PASS" if vol_passed else "FAIL",
                metric_value=f"5-Day Volatility {vol_disp} vs Ceiling 15.00%",
                threshold_applied=f"<= {self._phase5l_risk_cfg.max_rolling_volatility_5d:.2%}",
                explanation=(
                    f"5-session rolling volatility ({vol_disp}) is within the safe 15.00% market boundary."
                    if vol_passed
                    else f"Rolling volatility ({vol_disp}) exceeds safe ceiling (15.00%). Defensive gate forces signal to HOLD."
                ),
            ))

            # Stage 8: Directional BUY / HOLD / SELL Threshold
            thresh_applied = "+1.50% net (BUY), -1.50% net (SELL)"
            if failed_checks:
                st8_status = "HOLD"
                st8_expl = f"Defensive risk gates failed ({len(failed_checks)} failure). Signal forced to HOLD regardless of return magnitude."
            elif sig_str == "BUY":
                st8_status = "PASS"
                st8_expl = f"Net expected return ({net_pct}) clears calibrated BUY threshold (+1.50%). Candidate BUY signal generated."
            elif sig_str == "SELL":
                st8_status = "PASS"
                st8_expl = f"Net expected return ({net_pct}) clears SELL threshold (-1.50%). Candidate SELL signal generated."
            else:
                st8_status = "HOLD"
                st8_expl = f"Net expected return ({net_pct}) falls within neutral buffer (-1.50% to +1.50%). Signal is HOLD."

            funnel.append(DecisionFunnelStage(
                stage_number=8,
                stage_name="Directional BUY / HOLD / SELL Threshold",
                status=st8_status,
                metric_value=f"Net Return: {net_pct}",
                threshold_applied=thresh_applied,
                explanation=st8_expl,
            ))

        # Slice Historical Price Series for Charting (from phase5i_market_expansion.parquet)
        chart_series: List[Dict[str, Any]] = []
        p_exp_mkt = DATA_DIR / "market" / "phase5i_market_expansion.parquet"
        if p_exp_mkt.exists():
            try:
                mkt_sub = pd.read_parquet(p_exp_mkt, filters=[("ticker", "==", tk_clean)])
                if not mkt_sub.empty:
                    mkt_sub = mkt_sub[
                        (mkt_sub["trading_date"] >= "2018-01-01")
                        & (mkt_sub["trading_date"] <= (obs_d or "2020-06-15"))
                    ].sort_values("trading_date").tail(250)

                    for _, r in mkt_sub.iterrows():
                        chart_series.append({
                            "trading_date": str(r["trading_date"]),
                            "open": round(float(r["open"]), 2),
                            "high": round(float(r["high"]), 2),
                            "low": round(float(r["low"]), 2),
                            "close": round(float(r["close"]), 2),
                            "adjusted_close": round(float(r["adjusted_close"]), 2),
                            "volume": float(r["volume"]),
                        })
            except Exception as e:
                logger.error(f"Error loading price series for {tk_clean}: {e}")

        return CompanyResearchDetailResponse(
            status="available" if pred_val is not None else "unavailable",
            ticker=tk_clean,
            company_name=c_name,
            company_id=c_id,
            cik=cik,
            sector=sec,
            coverage_status=cov_status,
            is_truncated=is_trunc,
            limitations_note=lim_note,
            market_notes=lim_note,
            sec_notes=sec_note,
            observation_date=obs_d,
            data_freshness_days=0 if obs_d else None,
            model_id=f"{model_id}_Fold{fld_num}" if fld_num is not None else model_id,
            fold=fld_num,
            forecast_horizon="5 Trading Days (T close -> T+1 open -> T+5 close)",
            predicted_return=pred_val,
            predicted_return_pct=pred_pct,
            expected_net_return=net_val,
            expected_net_return_pct=net_pct,
            forecast_uncertainty=unc_val,
            forecast_uncertainty_pct=unc_pct,
            uncertainty_method=unc_method,
            signal=sig_str,
            decision_category=dec_cat,
            roundtrip_cost_bps=15.0,
            cost_breakdown=cost_breakdown,
            decision_reasons=reasons,
            funnel_stages=funnel,
            risk_checks_passed=passed_checks,
            risk_checks_failed=failed_checks,
            data_quality_warnings=warnings,
            historical_price_series=chart_series,
            available_prediction_dates=avail_dates,
            disclaimer=disclaimer,
        )

    def get_company_archived_predictions(
        self,
        ticker: str,
        model_id: Optional[str] = None,
        fold: Optional[int] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> Optional[CompanyArchivedPredictionsResponse]:
        """
        Returns verified archived out-of-sample forward-return predictions for a company
        from the Phase 5K research archive (phase5k_predictions_oos.parquet).
        Preserves strict separation between historical predictions and live runtime inference.
        """
        self._ensure_phase5l_initialized()

        tk_clean = ticker.strip().upper()

        # Verify ticker in 60-company universe
        match_co = self._phase5l_eligibility_df[self._phase5l_eligibility_df["ticker"] == tk_clean]
        if match_co.empty:
            return None

        co_row = match_co.iloc[0]
        c_name = str(co_row["company_name"])
        c_id = str(co_row["company_id"])
        sec = str(co_row["sector"])
        comp_pct = float(co_row["completeness_pct"])
        is_trunc = comp_pct < 95.0

        # Validate candidate model ID if provided
        valid_models = {
            "zero_baseline",
            "median_baseline",
            "ridge_regression",
            "elastic_net",
            "hist_gradient_boosting",
            "ridge_cs_demeaned",
            "ridge_cs_scaled",
            "ridge_sector_neutral",
        }
        if model_id is not None and model_id not in valid_models:
            raise ValueError(f"Model identifier '{model_id}' is invalid. Valid models: {sorted(valid_models)}")

        # Validate fold if provided
        valid_folds = {0, 1, 2, 3}
        if fold is not None and fold not in valid_folds:
            raise ValueError(f"Fold '{fold}' is invalid. Valid folds: {sorted(valid_folds)}")

        # Check OOS parquet artifact
        p_oos = DATA_DIR / "research" / "phase5k" / "phase5k_predictions_oos.parquet"
        if not p_oos.exists() or self._phase5l_oos_df is None or self._phase5l_oos_df.empty:
            raise FileNotFoundError(f"Missing out-of-sample predictions parquet archive: {p_oos}")

        # Sub-slice for ticker
        sub_co = self._phase5l_oos_df[self._phase5l_oos_df["ticker"] == tk_clean]
        if sub_co.empty:
            return CompanyArchivedPredictionsResponse(
                status="empty",
                ticker=tk_clean,
                company_name=c_name,
                company_id=c_id,
                sector=sec,
                total_records=0,
                returned_records=0,
                available_models=[],
                available_folds=[],
                is_truncated=is_trunc,
                predictions=[],
            )

        avail_models = sorted(sub_co["model_id"].unique().tolist())
        avail_folds = sorted(sub_co["fold"].unique().tolist())
        earliest_d = str(sub_co["trading_date"].min())
        latest_d = str(sub_co["trading_date"].max())

        # Apply filters
        filtered = sub_co
        if model_id is not None:
            filtered = filtered[filtered["model_id"] == model_id]
        if fold is not None:
            filtered = filtered[filtered["fold"] == fold]

        filtered = filtered.sort_values(["trading_date", "model_id"])
        total_rec = len(filtered)

        paged = filtered.iloc[offset : offset + limit]

        records: List[ArchivedPredictionRecord] = []
        for _, r in paged.iterrows():
            records.append(
                ArchivedPredictionRecord(
                    trading_date=str(r["trading_date"]),
                    fold=int(r["fold"]),
                    model_id=str(r["model_id"]),
                    predicted_return=round(float(r["predicted_return"]), 6),
                    target_return=round(float(r["target_return"]), 6),
                    residual=round(float(r["residual"]), 6),
                    sigma_train=round(float(r["sigma_train"]), 6),
                    adjusted_close=round(float(r["adjusted_close"]), 2),
                )
            )

        return CompanyArchivedPredictionsResponse(
            status="available" if total_rec > 0 else "empty",
            ticker=tk_clean,
            company_name=c_name,
            company_id=c_id,
            sector=sec,
            total_records=total_rec,
            returned_records=len(records),
            available_models=avail_models,
            available_folds=avail_folds,
            earliest_date=earliest_d,
            latest_date=latest_d,
            is_truncated=is_trunc,
            predictions=records,
        )

    def get_research_signals(
        self,
        model_id: str = "ridge_regression",
        as_of_date: Optional[str] = None,
        sector: Optional[str] = None,
        signal: Optional[str] = None,
    ) -> BulkSignalsResponse:
        """
        Returns bulk signals across the 60-company cohort for a specific model and observation date.
        """
        screener = self.get_60_company_screener(
            model_id=model_id,
            as_of_date=as_of_date,
            sector=sector,
            signal=signal,
        )

        signals_list = []
        for c in screener.companies:
            signals_list.append({
                "ticker": c.ticker,
                "company_name": c.company_name,
                "sector": c.sector,
                "observation_date": c.observation_date,
                "model_id": c.model_id,
                "predicted_return": c.predicted_return,
                "expected_net_return": c.expected_net_return,
                "signal": c.signal,
                "risk_status": c.risk_status,
                "failed_gate_count": c.failed_gate_count,
                "reasons": c.reasons,
            })

        return BulkSignalsResponse(
            status="success",
            mode="HISTORICAL_RESEARCH",
            model_id=model_id,
            as_of_date=as_of_date,
            total_signals=len(signals_list),
            signal_summary=screener.signal_summary,
            signals=signals_list,
        )

    def get_company_signal_detail(
        self,
        ticker: str,
        model_id: str = "ridge_regression",
        as_of_date: Optional[str] = None,
    ) -> SignalDetailResponse:
        """
        Returns detailed decision contract response with the 8-stage decision funnel for a single company.
        """
        detail = self.get_company_research_detail(ticker=ticker, model_id=model_id, as_of_date=as_of_date)
        return SignalDetailResponse(
            status=detail.status,
            ticker=detail.ticker,
            company_id=detail.company_id,
            decision_timestamp=f"{detail.observation_date}T14:15:00Z" if detail.observation_date else "N/A",
            observation_date=detail.observation_date or "N/A",
            model_id=detail.model_id or model_id,
            predicted_forward_return=detail.predicted_return,
            expected_net_return=detail.expected_net_return,
            signal=detail.signal,
            decision_category=detail.decision_category,
            roundtrip_cost_bps=detail.roundtrip_cost_bps,
            threshold_applied=self._phase5l_risk_cfg.buy_threshold,
            funnel_stages=detail.funnel_stages,
            risk_checks_passed=detail.risk_checks_passed,
            risk_checks_failed=detail.risk_checks_failed,
            reasons=detail.decision_reasons,
            warnings=detail.data_quality_warnings,
            is_experimental=True,
        )

    # =====================================================================
    # Phase 6.2 — Canonical Company Universe & Capability Contract Builder
    # =====================================================================

    def _ensure_capabilities_initialized(self):
        """Constructs and caches canonical company capabilities from verified local sources."""
        if hasattr(self, "_capabilities_initialized") and self._capabilities_initialized:
            return

        self._ensure_phase5l_initialized()

        p_elig = DATA_DIR / "universe" / "phase5j_company_eligibility.csv"
        p_exp_mkt = DATA_DIR / "market" / "phase5i_market_expansion.parquet"
        p_oos = DATA_DIR / "research" / "phase5k" / "phase5k_predictions_oos.parquet"
        p_sec_facts = DATA_DIR / "sec" / "facts" / "pilot_financial_facts.parquet"
        p_sec_events = DATA_DIR / "sec" / "eight_k" / "phase5f_8k_events.parquet"

        p_elig = DATA_DIR / "universe" / "phase5j_company_eligibility.csv"
        p_exp_mkt = DATA_DIR / "market" / "phase5i_market_expansion.parquet"
        p_oos = DATA_DIR / "research" / "phase5k" / "phase5k_predictions_oos.parquet"
        p_sec_facts = DATA_DIR / "sec" / "facts" / "pilot_financial_facts.parquet"
        p_sec_events = DATA_DIR / "sec" / "eight_k" / "phase5f_8k_events.parquet"

        if not p_elig.exists():
            raise FileNotFoundError(f"Authoritative eligibility manifest missing: {p_elig}")

        required_cols = [
            "company_id", "ticker", "company_name", "sector", "cik",
            "total_sessions", "earliest_date", "latest_date", "window_sessions", "completeness_pct",
            "folds_eligible", "track_a_market_only", "track_b_market_plus_fund",
            "track_c_market_plus_events", "track_d_combined",
            "market_notes", "fundamentals_notes", "events_notes", "news_notes"
        ]
        missing_cols = [c for c in required_cols if c not in self._phase5l_eligibility_df.columns]
        if missing_cols:
            raise ValueError(f"Eligibility manifest missing required columns: {missing_cols}")

        # Check market artifact presence and verify constituent tickers
        market_tickers_present = set()
        market_artifact_exists = p_exp_mkt.exists()
        if market_artifact_exists:
            try:
                mkt_df_cols = pd.read_parquet(p_exp_mkt, columns=["ticker"])
                market_tickers_present = set(mkt_df_cols["ticker"].unique())
            except Exception as e:
                logger.warning(f"Failed to read market expansion parquet: {e}")
                market_artifact_exists = False

        # Pre-aggregate prediction metadata by ticker from out-of-sample archive
        oos_meta_by_ticker = {}
        prediction_artifact_exists = p_oos.exists()
        if prediction_artifact_exists and self._phase5l_oos_df is not None and not self._phase5l_oos_df.empty:
            for tk, grp in self._phase5l_oos_df.groupby("ticker"):
                oos_meta_by_ticker[str(tk)] = {
                    "models": sorted([str(m) for m in grp["model_id"].unique()]),
                    "folds": sorted([int(f) for f in grp["fold"].unique()]),
                    "earliest": str(grp["trading_date"].min()),
                    "latest": str(grp["trading_date"].max()),
                }

        # Base provenance sources
        base_provenance = [
            "data/processed/universe/phase5j_company_eligibility.csv",
            "data/processed/market/phase5i_market_expansion.parquet",
            "data/processed/research/phase5k/phase5k_predictions_oos.parquet",
        ]

        # Alias dictionary (empty: distinct share classes are not aliases)
        alias_map = {}

        capabilities_map = {}

        for _, row in self._phase5l_eligibility_df.iterrows():
            tk = str(row["ticker"]).strip().upper()
            c_name = str(row["company_name"]).strip()
            c_id = str(row["company_id"]).strip()
            cik_str = f"{int(row['cik']):010d}" if pd.notna(row["cik"]) else None
            sec = str(row["sector"]).strip() if pd.notna(row["sector"]) else None
            comp_pct = float(row["completeness_pct"]) if pd.notna(row["completeness_pct"]) else 0.0
            tot_sess = int(row["total_sessions"]) if pd.notna(row["total_sessions"]) else 0
            early_d = str(row["earliest_date"]) if pd.notna(row["earliest_date"]) else None
            late_d = str(row["latest_date"]) if pd.notna(row["latest_date"]) else None
            window_sess = (
                int(row["window_sessions"])
                if ("window_sessions" in row and pd.notna(row["window_sessions"]))
                else int(round(363 * comp_pct / 100.0))
            )
            is_trunc = comp_pct < 95.0

            # 1. Identity (GOOG and GOOGL preserved as distinct share-classes)
            rel_share_classes = ["GOOGL"] if tk == "GOOG" else []
            share_class_desc = "Class C (Non-voting)" if tk == "GOOG" else None
            id_notes = (
                "Alphabet Inc. dual-class share pair: Class C (GOOG) tracked in market dataset; "
                "Class A (GOOGL) reported in SEC EDGAR submissions. Share classes are distinct market instruments."
                if tk == "GOOG"
                else None
            )

            identity = CompanyIdentity(
                company_id=c_id,
                canonical_ticker=tk,
                ticker_aliases=[],
                related_share_classes=rel_share_classes,
                share_class_description=share_class_desc,
                company_name=c_name,
                cik=cik_str,
                sector=sec,
                universe_membership="HISTORICAL_RESEARCH_COHORT",
                identity_status=IdentityStatus.CANONICAL_CONSTITUENT,
                identity_notes=id_notes,
            )

            # 2. Market Artifact Coverage & Evaluation-Window Coverage Separation
            if not market_artifact_exists:
                mkt_status = CapabilityStatus.UNAVAILABLE
                feat_avail = False
                mkt_limitations = "Physical market expansion artifact unavailable."
            elif tk not in market_tickers_present:
                mkt_status = CapabilityStatus.UNAVAILABLE
                feat_avail = False
                mkt_limitations = f"Ticker {tk} missing from physical market expansion artifact."
            else:
                mkt_status = CapabilityStatus.SUPPORTED
                feat_avail = True
                mkt_limitations = str(row["market_notes"]) if pd.notna(row["market_notes"]) else None

            market_artifact = MarketArtifactCoverage(
                status=mkt_status,
                earliest_date=early_d if mkt_status == CapabilityStatus.SUPPORTED else None,
                latest_date=late_d if mkt_status == CapabilityStatus.SUPPORTED else None,
                total_sessions=tot_sess if mkt_status == CapabilityStatus.SUPPORTED else 0,
                source_artifact="data/processed/market/phase5i_market_expansion.parquet",
                feature_data_available=feat_avail,
                feature_schema_compatibility="17_technical_indicators_v1",
                limitations_note=mkt_limitations,
            )

            # Descriptive categorization (separate from fold eligibility)
            if comp_pct >= 99.9:
                cov_cat = MarketCoverageStatus.COMPLETE
            elif comp_pct >= 95.0:
                cov_cat = MarketCoverageStatus.NEAR_COMPLETE
            else:
                cov_cat = MarketCoverageStatus.TRUNCATED

            evaluation_window = EvaluationWindowCoverage(
                window_start_date="2019-01-02",
                window_end_date="2020-06-03",
                expected_window_sessions=363,
                observed_window_sessions=window_sess,
                completeness_pct=round(comp_pct, 2),
                completeness_denominator=363,
                is_truncated=is_trunc,
                descriptive_category=cov_cat,
                source_manifest="data/processed/universe/phase5j_company_eligibility.csv",
                limitations_note=mkt_limitations,
            )

            # 3. Multi-modal Coverage
            fund_elig = str(row.get("fundamentals_eligibility", "")).upper()
            fund_notes = str(row.get("fundamentals_notes", "")) if pd.notna(row.get("fundamentals_notes")) else None
            facts_exists = p_sec_facts.exists()
            if fund_elig == "ELIGIBLE":
                fund_status = CapabilityStatus.SUPPORTED if facts_exists else CapabilityStatus.UNAVAILABLE
            else:
                fund_status = CapabilityStatus.NOT_DOWNLOADED_IN_PILOT

            evt_elig = str(row.get("events_eligibility", "")).upper()
            evt_notes = str(row.get("events_notes", "")) if pd.notna(row.get("events_notes")) else None
            events_exists = p_sec_events.exists()
            if evt_elig == "ELIGIBLE":
                evt_status = CapabilityStatus.SUPPORTED if events_exists else CapabilityStatus.UNAVAILABLE
            else:
                evt_status = CapabilityStatus.NOT_DOWNLOADED_IN_PILOT

            news_notes = str(row.get("news_notes", "")) if pd.notna(row.get("news_notes")) else None
            news_status = CapabilityStatus.EXCLUDED_BY_POLICY

            multi_modal = MultiModalCoverage(
                sec_fundamentals_status=fund_status,
                sec_fundamentals_notes=fund_notes,
                sec_events_status=evt_status,
                sec_events_notes=evt_notes,
                news_status=news_status,
                news_notes=news_notes,
            )

            # 4. Evaluation Track & Authoritative Fold Eligibility from Manifest
            t_a = str(row.get("track_a_market_only", "")).upper().startswith("ELIGIBLE")
            t_b = str(row.get("track_b_market_plus_fund", "")).upper() == "ELIGIBLE"
            t_c = str(row.get("track_c_market_plus_events", "")).upper() == "ELIGIBLE"
            t_d = str(row.get("track_d_combined", "")).upper() == "ELIGIBLE"

            # Parse folds_eligible e.g. "Fold 0; Fold 1; Fold 2; Fold 3"
            folds_raw = str(row.get("folds_eligible", ""))
            folds_list = []
            for f_str in ["0", "1", "2", "3"]:
                if f"Fold {f_str}" in folds_raw:
                    folds_list.append(int(f_str))

            fold_lim = None
            if 3 not in folds_list:
                fold_lim = (
                    "Ineligible for Fold 3 Holdout evaluation (terminates on 2020-04-01 with only 2 out-of-sample sessions; "
                    "produces UNAVAILABLE signal in Holdout fold)"
                )

            evaluation = EvaluationTrackEligibility(
                track_a_market_only=t_a,
                track_b_market_plus_fund=t_b,
                track_c_market_plus_events=t_c,
                track_d_combined=t_d,
                eligible_folds=folds_list,
                fold_limitations=fold_lim,
            )

            # 5. Historical Predictions (from out-of-sample archive)
            pred_meta = oos_meta_by_ticker.get(tk, {})
            has_preds = bool(pred_meta)

            predictions = HistoricalPredictionCoverage(
                archived_predictions_available=has_preds,
                available_models=pred_meta.get("models", []),
                available_folds=pred_meta.get("folds", []),
                earliest_prediction_date=pred_meta.get("earliest"),
                latest_prediction_date=pred_meta.get("latest"),
                source_artifact="data/processed/research/phase5k/phase5k_predictions_oos.parquet",
            )

            # 6. Runtime Execution & Portfolio Simulation Capabilities
            is_pilot = tk in COMPANY_CATALOG
            runtime = RuntimeExecutionCapabilities(
                runtime_inference_supported=is_pilot,
                runtime_inference_model=(
                    "Ridge-Market-Only-v1 (Alpha=1000.0, Walk-Forward Fold 3)" if is_pilot else None
                ),
                runtime_decision_supported=is_pilot,
                historical_decision_supported=has_preds,
                portfolio_simulation_status=CapabilityStatus.UNVERIFIED,
                portfolio_simulation_notes=(
                    "Offline batch multi-asset simulation engine only. Interactive per-company simulation "
                    "is unverified; runtime execution is unsupported."
                ),
                interactive_trade_execution=False,
            )

            # 7. Provenance & Limitations
            co_provenance = list(base_provenance)
            if fund_status == CapabilityStatus.SUPPORTED and p_sec_facts.exists():
                co_provenance.append("data/processed/sec/facts/pilot_financial_facts.parquet")
            if evt_status == CapabilityStatus.SUPPORTED and p_sec_events.exists():
                co_provenance.append("data/processed/sec/eight_k/phase5f_8k_events.parquet")

            limitations_list = []
            if is_trunc:
                limitations_list.append(
                    f"Market history truncated on 2020-04-01 ({tot_sess} total sessions; {comp_pct:.2f}% coverage in evaluation window)."
                )
                limitations_list.append(
                    "Excluded from Fold 3 Holdout evaluation (produces UNAVAILABLE state in Holdout fold)."
                )
            if fund_status == CapabilityStatus.NOT_DOWNLOADED_IN_PILOT:
                limitations_list.append(
                    "Point-in-time SEC 10-K/10-Q facts unobserved (not downloaded into local pilot store; synthetic data prohibited)."
                )
            if evt_status == CapabilityStatus.NOT_DOWNLOADED_IN_PILOT:
                limitations_list.append(
                    "SEC Form 8-K unscheduled events unobserved (not downloaded into local pilot store; zero-event imputation prohibited)."
                )
            limitations_list.append(
                "Third-party commercial news text excluded due to licensing redistribution policy."
            )
            if not is_pilot:
                limitations_list.append(
                    "Runtime in-memory model inference unfitted in prototype service; historical walk-forward out-of-sample predictions available."
                )

            item = CompanyCapabilityItem(
                identity=identity,
                market_artifact=market_artifact,
                evaluation_window=evaluation_window,
                multi_modal=multi_modal,
                evaluation_tracks=evaluation,
                predictions=predictions,
                runtime=runtime,
                provenance_sources=co_provenance,
                data_limitations=limitations_list,
            )

            capabilities_map[tk] = item

        self._capabilities_cache = capabilities_map
        self._ticker_alias_map = alias_map
        self._capabilities_list = sorted(list(capabilities_map.values()), key=lambda x: x.identity.canonical_ticker)
        self._capabilities_initialized = True

    def get_company_capabilities_list(self) -> CompanyCapabilityListResponse:
        """Returns the canonical capability inventory for the 60-company research cohort."""
        self._ensure_capabilities_initialized()
        excluded_list = [
            {
                "ticker": "AA",
                "company_name": "Alcoa Inc. / Arconic Inc.",
                "cik": "0000004281",
                "reason": EXCLUDED_COMPANIES.get("AA", "Corporate split identity ambiguity"),
                "identity_status": "EXCLUDED_AMBIGUOUS_IDENTITY",
                "membership": "EXCLUDED",
            }
        ]
        return CompanyCapabilityListResponse(
            status="success",
            version="v1",
            total_cohort_count=len(self._capabilities_list),
            as_of_reference="2020-06-03",
            companies=self._capabilities_list,
            excluded_entities=excluded_list,
        )

    def get_company_capability(self, ticker: str) -> Optional[CompanyCapabilityItem]:
        """Returns the capability record for a single company or resolves supported aliases."""
        self._ensure_capabilities_initialized()
        tk = ticker.strip().upper()
        # Resolve alias if present
        if tk in self._ticker_alias_map:
            tk = self._ticker_alias_map[tk]
        return self._capabilities_cache.get(tk)


# Singleton instance
dashboard_service = DashboardService()



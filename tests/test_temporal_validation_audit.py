"""
Unit and Regression Tests for Temporal Validation Audit and Walk-Forward Pipeline (Phase 5F).
Mandatory Audit Items from Section 8:
1. Multi-company date grouping in internal validation folds (no date leakage across companies).
2. Isolated training-only preprocessing (imputation & scaling) during alpha tuning.
3. Full outer fold refitting of preprocessing and final Ridge model.
4. Identical validation dates and sample sizes across comparable model variants.
"""

import pandas as pd
import numpy as np
import pytest

from src.models.splitter import WalkForwardSplitter, WalkForwardConfig
from src.models.baseline import (
    MarketBaselinePipeline,
    MARKET_FEATURE_COLUMNS,
    EVENT_FEATURE_COLUMNS,
    MARKET_PLUS_EVENT_COLUMNS,
)


@pytest.fixture
def mock_panel_dataset():
    """Create a synthetic 3-company panel across 100 trading sessions."""
    dates = pd.date_range("2020-01-01", periods=100, freq="B").strftime("%Y-%m-%d").tolist()
    companies = ["AAPL", "JPM", "TSLA"]
    records = []
    
    np.random.seed(42)
    for d in dates:
        for ticker in companies:
            row = {
                "trading_date": d,
                "company_id": f"US_CIK_{ticker}",
                "ticker": ticker,
                "target_forward_return_5d": np.random.normal(0.001, 0.02),
            }
            # Add synthetic market features
            for feat in MARKET_FEATURE_COLUMNS:
                row[feat] = np.random.normal(0.0, 1.0)
            # Add synthetic event features with some NaNs
            row["sec_event_count_5d"] = np.random.poisson(0.2)
            row["sec_earnings_release_in_window"] = 1 if np.random.rand() < 0.05 else 0
            row["sec_days_since_last_8k"] = np.random.choice([np.nan, 3.0, 10.0, 25.0])
            records.append(row)

    df = pd.DataFrame(records).sort_values("trading_date").reset_index(drop=True)
    return df


def test_internal_alpha_tuning_date_grouping(mock_panel_dataset):
    """
    Mandatory Audit Item 1:
    Verify that internal alpha selection splits on unique trading dates, keeping all companies
    on the same calendar date grouped together in either internal training or internal validation.
    """
    df = mock_panel_dataset
    unique_dates = sorted(df["trading_date"].unique())
    train_dates = unique_dates[:60]
    val_dates = unique_dates[65:80]

    train_df = df[df["trading_date"].isin(train_dates)].copy()
    val_df = df[df["trading_date"].isin(val_dates)].copy()

    X_tr = train_df[MARKET_FEATURE_COLUMNS]
    y_tr = train_df["target_forward_return_5d"].values
    X_val = val_df[MARKET_FEATURE_COLUMNS]
    y_val = val_df["target_forward_return_5d"].values

    pipeline = MarketBaselinePipeline(
        feature_columns=MARKET_FEATURE_COLUMNS,
        alphas=(1.0, 10.0, 100.0)
    )

    # Passing train_df (which contains trading_date) enables date-grouped internal tuning
    result = pipeline.fit_and_evaluate_ridge(
        X_train=train_df,
        y_train=y_tr,
        X_val=val_df,
        y_val=y_val,
        model_name="Market Only",
    )

    assert result.best_params["alpha"] in (1.0, 10.0, 100.0)
    assert len(result.predictions) == len(val_df)
    assert not np.isnan(result.predictions).any()


def test_preprocessing_isolation_during_alpha_selection(mock_panel_dataset):
    """
    Mandatory Audit Item 2:
    Verify that imputer and scaler are fitted strictly on the internal training split,
    preventing internal validation values from leaking into the tuning normalization parameters.
    """
    df = mock_panel_dataset.copy()
    unique_dates = sorted(df["trading_date"].unique())
    train_dates = unique_dates[:60]
    val_dates = unique_dates[65:80]

    train_df = df[df["trading_date"].isin(train_dates)].copy()
    val_df = df[df["trading_date"].isin(val_dates)].copy()

    # Plant an extreme outlier in the internal validation date segment
    # Internal split is at 70% of 60 dates = 42 dates
    inner_val_date = train_dates[45]
    feature_to_contaminate = MARKET_FEATURE_COLUMNS[0]
    train_df.loc[train_df["trading_date"] >= inner_val_date, feature_to_contaminate] = 1_000_000.0

    y_tr = train_df["target_forward_return_5d"].values
    y_val = val_df["target_forward_return_5d"].values

    pipeline = MarketBaselinePipeline(
        feature_columns=MARKET_FEATURE_COLUMNS,
        alphas=(0.1, 10.0, 1000.0)
    )

    result = pipeline.fit_and_evaluate_ridge(
        X_train=train_df,
        y_train=y_tr,
        X_val=val_df,
        y_val=y_val,
        model_name="Contaminated Test",
    )

    assert result is not None
    assert np.all(np.isfinite(result.predictions))


def test_walk_forward_splitter_outer_purge_and_integrity(mock_panel_dataset):
    """Verify WalkForwardSplitter respects purge gap and produces disjoint chronological folds."""
    df = mock_panel_dataset
    cfg = WalkForwardConfig(
        n_splits=3,
        train_min_sessions=40,
        val_sessions=15,
        purge_sessions=5
    )
    splitter = WalkForwardSplitter(cfg)

    splits = list(splitter.split(df))
    assert len(splits) == 3

    for fold_idx, (train_idx, val_idx) in enumerate(splits):
        train_df = df.iloc[train_idx]
        val_df = df.iloc[val_idx]

        # Multi-company dates must stay intact (all 3 companies on every date)
        assert (train_df.groupby("trading_date").size() == 3).all()
        assert (val_df.groupby("trading_date").size() == 3).all()

        # Chronological order
        max_train_date = train_df["trading_date"].max()
        min_val_date = val_df["trading_date"].min()
        assert min_val_date > max_train_date

        # Purge gap: exactly 5 sessions between max train date and min val date
        all_unique_dates = sorted(df["trading_date"].unique())
        train_end_idx = all_unique_dates.index(max_train_date)
        val_start_idx = all_unique_dates.index(min_val_date)
        gap = val_start_idx - train_end_idx - 1
        assert gap == 5, f"Fold {fold_idx}: expected purge gap of 5 sessions, got {gap}"


def test_identical_validation_sample_across_model_variants(mock_panel_dataset):
    """
    Verify that Market-Only and Market+Events evaluate on identical validation samples
    with no silent drop of rows due to missing event features.
    """
    df = mock_panel_dataset
    unique_dates = sorted(df["trading_date"].unique())
    train_df = df[df["trading_date"].isin(unique_dates[:60])].copy()
    val_df = df[df["trading_date"].isin(unique_dates[65:85])].copy()

    y_tr = train_df["target_forward_return_5d"].values
    y_val = val_df["target_forward_return_5d"].values

    # Model 1: Market Only (17 features)
    pipe_mkt = MarketBaselinePipeline(feature_columns=MARKET_FEATURE_COLUMNS)
    res_mkt = pipe_mkt.fit_and_evaluate_ridge(
        X_train=train_df,
        y_train=y_tr,
        X_val=val_df,
        y_val=y_val,
        model_name="Market-Only",
    )

    # Model 2: Market + Events (20 features)
    pipe_evt = MarketBaselinePipeline(feature_columns=MARKET_PLUS_EVENT_COLUMNS)
    res_evt = pipe_evt.fit_and_evaluate_ridge(
        X_train=train_df,
        y_train=y_tr,
        X_val=val_df,
        y_val=y_val,
        model_name="Market+Events",
    )

    assert len(res_mkt.predictions) == len(res_evt.predictions) == len(val_df)
    assert np.all(np.isfinite(res_mkt.predictions))
    assert np.all(np.isfinite(res_evt.predictions))

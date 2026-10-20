"""
Unit Tests for Market Feature Engineering.

Validates technical indicators, adjusted price semantics, stock-split handling,
insufficient lookback protection, corporate identity isolation, and determinism.
"""

import numpy as np
import pandas as pd
import pytest

from src.features.config import MarketFeatureConfig, DecisionTimingMode
from src.features.market import MarketFeatureEngine


@pytest.fixture
def sample_market_series():
    """Generates a controlled 30-day market time series for testing."""
    dates = pd.date_range("2023-01-03", periods=30, freq="B")
    records = []
    base_price = 100.0

    for i, dt in enumerate(dates):
        # 1% alternating drift
        price = base_price * (1.0 + 0.01 * (1 if i % 2 == 0 else -1))
        trading_date = dt.strftime("%Y-%m-%d")
        records.append({
            "company_id": "US_CIK_0000320193",
            "ticker": "AAPL",
            "timestamp": pd.to_datetime(f"{trading_date} 00:00:00", utc=True),
            "trading_date": trading_date,
            "open": price * 0.99,
            "high": price * 1.02,
            "low": price * 0.98,
            "close": price,
            "adjusted_open": price * 0.99,
            "adjusted_high": price * 1.02,
            "adjusted_low": price * 0.98,
            "adjusted_close": price,
            "volume": 1000000 + i * 10000,
            "adjusted_volume": 1000000 + i * 10000,
            "dividend_cash": 0.0,
            "split_factor": 1.0,
            "source": "tiingo_test",
        })
    return pd.DataFrame(records)


class TestMarketFeatureEngine:
    def test_returns_and_log_returns(self, sample_market_series):
        engine = MarketFeatureEngine()
        df_feat = engine.compute_features(sample_market_series)

        # First row must be NaN for 1d returns
        assert np.isnan(df_feat.iloc[0]["market_return_1d"])
        assert np.isnan(df_feat.iloc[0]["market_log_return_1d"])
        assert bool(df_feat.iloc[0]["market_return_1d_missing"]) is True

        # Second row: check formula
        p0 = sample_market_series.iloc[0]["adjusted_close"]
        p1 = sample_market_series.iloc[1]["adjusted_close"]
        expected_ret = (p1 - p0) / p0
        expected_log_ret = np.log(p1 / p0)

        assert pytest.approx(df_feat.iloc[1]["market_return_1d"], rel=1e-5) == expected_ret
        assert pytest.approx(df_feat.iloc[1]["market_log_return_1d"], rel=1e-5) == expected_log_ret
        assert bool(df_feat.iloc[1]["market_return_1d_missing"]) is False

    def test_stock_split_adjusted_returns(self):
        """
        Critical test: A 4-for-1 stock split occurs on day 2.
        Unadjusted close drops from $400 to $100.
        Adjusted close moves from $100 to $101 (+1% economic return).
        Returns MUST be +1%, NOT -75%!
        """
        records = [
            {
                "company_id": "US_CIK_0000320193",
                "ticker": "AAPL",
                "timestamp": pd.to_datetime("2020-08-28 00:00:00", utc=True),
                "trading_date": "2020-08-28",
                "open": 400.0, "high": 405.0, "low": 395.0, "close": 400.0,
                "adjusted_open": 100.0, "adjusted_high": 101.25, "adjusted_low": 98.75, "adjusted_close": 100.0,
                "volume": 20000000, "adjusted_volume": 80000000,
                "dividend_cash": 0.0, "split_factor": 1.0,
            },
            {
                "company_id": "US_CIK_0000320193",
                "ticker": "AAPL",
                "timestamp": pd.to_datetime("2020-08-31 00:00:00", utc=True),
                "trading_date": "2020-08-31",
                # Day of 4:1 split
                "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0,
                "adjusted_open": 100.0, "adjusted_high": 102.0, "adjusted_low": 99.0, "adjusted_close": 101.0,
                "volume": 80000000, "adjusted_volume": 80000000,
                "dividend_cash": 0.0, "split_factor": 4.0,
            },
        ]
        df = pd.DataFrame(records)
        engine = MarketFeatureEngine()
        df_feat = engine.compute_features(df)

        # Return on day 2 must be (101 - 100)/100 = +0.01 (+1%)
        ret_day2 = df_feat.iloc[1]["market_return_1d"]
        assert pytest.approx(ret_day2, rel=1e-5) == 0.01
        # Must definitely NOT be -0.7475 (-74.75%)
        assert ret_day2 > 0

    def test_insufficient_lookback_yields_nan_no_imputation(self, sample_market_series):
        """Verifies that lookbacks larger than available history yield NaN, never forward/backfilled."""
        # Restrict input to only 5 trading days
        df_short = sample_market_series.iloc[:5].copy()
        engine = MarketFeatureEngine()
        df_feat = engine.compute_features(df_short)

        # 21-day momentum, 20-day SMA, 63-day volatility must all be NaN for all 5 rows
        assert df_feat["market_momentum_21d"].isna().all()
        assert df_feat["market_momentum_21d_missing"].all()

        assert df_feat["market_sma_20d"].isna().all()
        assert df_feat["market_sma_20d_missing"].all()

        assert df_feat["market_volatility_21d"].isna().all()
        assert df_feat["market_volatility_21d_missing"].all()

    def test_rsi_calculation_bounds(self, sample_market_series):
        engine = MarketFeatureEngine()
        df_feat = engine.compute_features(sample_market_series)

        # For rows with valid RSI (row 14+), RSI must be between 0 and 100
        valid_rsi = df_feat["market_rsi_14d"].dropna()
        assert len(valid_rsi) > 0
        assert (valid_rsi >= 0.0).all()
        assert (valid_rsi <= 100.0).all()

    def test_recycled_ticker_isolation(self):
        """
        Critical test: Two distinct companies (e.g. historical Monsanto and 2021 SPAC)
        both using ticker 'MON' must NOT have returns computed across their boundary!
        """
        records = [
            # Company A: Monsanto Company (2018)
            {
                "company_id": "US_CIK_0001110783",
                "ticker": "MON",
                "timestamp": pd.to_datetime("2018-06-05 00:00:00", utc=True),
                "trading_date": "2018-06-05",
                "open": 125.0, "high": 126.0, "low": 124.0, "close": 125.0,
                "adjusted_open": 125.0, "adjusted_high": 126.0, "adjusted_low": 124.0, "adjusted_close": 125.0,
                "volume": 5000000,
            },
            # Company B: Monument Circle SPAC (2021)
            {
                "company_id": "US_CIK_0001844200",
                "ticker": "MON",
                "timestamp": pd.to_datetime("2021-03-16 00:00:00", utc=True),
                "trading_date": "2021-03-16",
                "open": 9.80, "high": 9.90, "low": 9.75, "close": 9.80,
                "adjusted_open": 9.80, "adjusted_high": 9.90, "adjusted_low": 9.75, "adjusted_close": 9.80,
                "volume": 200000,
            },
        ]
        df = pd.DataFrame(records)
        engine = MarketFeatureEngine()
        df_feat = engine.compute_features(df)

        # Company B's return on 2021-03-16 must be NaN (first observation for that company)
        # It must NOT calculate (9.80 - 125.0)/125.0 = -92%!
        spac_row = df_feat[df_feat["company_id"] == "US_CIK_0001844200"].iloc[0]
        assert np.isnan(spac_row["market_return_1d"])
        assert bool(spac_row["market_return_1d_missing"]) is True

    def test_decision_timing_modes(self, sample_market_series):
        # Sample series starts on 2023-01-03 (Winter, EST, UTC-5)
        # Mode 1: MARKET_CLOSE (16:00 ET = 21:00 UTC in winter EST)
        cfg_close = MarketFeatureConfig(decision_timing=DecisionTimingMode.MARKET_CLOSE)
        df_close = MarketFeatureEngine(cfg_close).compute_features(sample_market_series)
        d_close = df_close.iloc[0]["decision_timestamp"]
        assert d_close.hour == 21
        assert d_close.minute == 0
        assert str(d_close.date()) == sample_market_series.iloc[0]["trading_date"]

        # Mode 2: NEXT_SESSION_OPEN unbuffered (Next trading day 2023-01-04 09:30 ET = 14:30 UTC in winter EST)
        cfg_open = MarketFeatureConfig(decision_timing=DecisionTimingMode.NEXT_SESSION_OPEN)
        df_open = MarketFeatureEngine(cfg_open).compute_features(sample_market_series)
        d_open = df_open.iloc[0]["decision_timestamp"]
        assert d_open.hour == 14
        assert d_open.minute == 30
        assert d_open == pd.Timestamp("2023-01-04 14:30:00", tz="UTC")
        assert d_open > d_close

        # Mode 3: NEXT_SESSION_OPEN with pre_open_cutoff_minutes=15 (09:15 ET = 14:15 UTC in winter EST)
        cfg_open_buffered = MarketFeatureConfig(
            decision_timing=DecisionTimingMode.NEXT_SESSION_OPEN,
            pre_open_cutoff_minutes=15,
        )
        df_open_buffered = MarketFeatureEngine(cfg_open_buffered).compute_features(sample_market_series)
        d_open_buffered = df_open_buffered.iloc[0]["decision_timestamp"]
        assert d_open_buffered.hour == 14
        assert d_open_buffered.minute == 15
        assert d_open_buffered == pd.Timestamp("2023-01-04 14:15:00", tz="UTC")
        assert d_open > d_open_buffered > d_close

    def test_deterministic_reproducibility(self, sample_market_series):
        engine = MarketFeatureEngine()
        df1 = engine.compute_features(sample_market_series)
        df2 = engine.compute_features(sample_market_series)

        pd.testing.assert_frame_equal(df1, df2)

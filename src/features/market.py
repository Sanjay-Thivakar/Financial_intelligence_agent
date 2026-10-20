"""
Market Feature Engineering Module.

Computes point-in-time, deterministic technical and price-action features
from normalized daily market data. Preserves adjusted vs unadjusted price
semantics, isolates corporate identities, and avoids look-ahead leakage.
"""

import logging
from typing import Dict, List, Optional
import numpy as np
import pandas as pd

from src.features.config import MarketFeatureConfig, DecisionTimingMode
from src.features.calendar import MarketCalendar

logger = logging.getLogger(__name__)


class MarketFeatureEngine:
    """Computes technical and price-action features across historical market observations."""

    def __init__(self, config: Optional[MarketFeatureConfig] = None):
        self.config = config or MarketFeatureConfig()

    def compute_features(self, df_market: pd.DataFrame) -> pd.DataFrame:
        """
        Computes all market features for the given market dataset.
        Guarantees:
        1. Groups strictly by `company_id` to prevent cross-company leakage.
        2. Sorts chronologically by `trading_date` within each company.
        3. Uses `adjusted_close` for returns, volatility, momentum, and RSI
           to avoid incorrectly interpreting stock splits as economic returns.
        4. Leaves insufficient lookback values as NaN (no future-data imputation).
        5. Generates explicit missing-data indicators.
        6. Attaches `decision_timestamp` according to configured timing mode.
        """
        if df_market.empty:
            return pd.DataFrame()

        # Validate required columns
        required_cols = [
            "company_id", "ticker", "timestamp", "trading_date",
            "open", "high", "low", "close", "adjusted_close", "volume"
        ]
        missing = [c for c in required_cols if c not in df_market.columns]
        if missing:
            raise ValueError(f"Market DataFrame missing required columns: {missing}")

        # Process each company independently to prevent identity bleeding
        feature_frames = []
        for company_id, comp_df in df_market.groupby("company_id", sort=False):
            comp_features = self._compute_company_features(comp_df.copy())
            feature_frames.append(comp_features)

        result_df = pd.concat(feature_frames, ignore_index=True)
        return result_df

    def _compute_company_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Computes technical features for a single company time series."""
        # Ensure unique trading sessions and chronological ordering
        df = df.drop_duplicates(subset=["trading_date"], keep="last").sort_values(by="trading_date").reset_index(drop=True)

        # 1. Base Prices & Corporate Actions (guarded against non-positive anomalies)
        adj_close = df["adjusted_close"].astype(float)
        adj_close = pd.Series(np.where(adj_close > 0, adj_close, np.nan), index=df.index)
        close = df["close"].astype(float)
        volume = df["volume"].astype(float)

        # 2. Returns (using adjusted close)
        # 1-day simple return: (P_t - P_{t-1}) / P_{t-1}
        ret_1d = adj_close.pct_change(periods=1)
        # 1-day log return: ln(P_t / P_{t-1})
        log_ret_1d = np.log(adj_close / adj_close.shift(1))

        df["market_return_1d"] = ret_1d
        df["market_log_return_1d"] = log_ret_1d
        df["market_return_1d_missing"] = ret_1d.isna()

        # Configurable multi-day returns
        for w in self.config.return_windows:
            if w == 1:
                continue
            ret_w = adj_close.pct_change(periods=w)
            df[f"market_return_{w}d"] = ret_w
            df[f"market_return_{w}d_missing"] = ret_w.isna()

        # 3. Momentum (Price Relative Ratio: P_t / P_{t-k} - 1.0)
        for w in self.config.momentum_windows:
            mom_w = (adj_close / adj_close.shift(w)) - 1.0
            df[f"market_momentum_{w}d"] = mom_w
            df[f"market_momentum_{w}d_missing"] = mom_w.isna()

        # 4. Rolling Volatility (annualized std of daily log returns)
        ann_factor = np.sqrt(self.config.annualization_factor)
        for w in self.config.volatility_windows:
            # Requires at least w periods to avoid premature or biased estimates
            vol_unann = log_ret_1d.rolling(window=w, min_periods=w).std()
            vol_ann = vol_unann * ann_factor
            df[f"market_volatility_{w}d"] = vol_ann
            df[f"market_volatility_{w}d_unannualized"] = vol_unann
            df[f"market_volatility_{w}d_missing"] = vol_ann.isna()

        # 5. Rolling Price Mean, Standard Deviation, and Z-Score
        for w in self.config.rolling_mean_windows:
            roll_mean = adj_close.rolling(window=w, min_periods=w).mean()
            roll_std = adj_close.rolling(window=w, min_periods=w).std()
            # Distance from rolling mean in standard deviations (Z-score)
            z_score = np.where(roll_std > 0, (adj_close - roll_mean) / roll_std, np.nan)

            df[f"market_sma_{w}d"] = roll_mean
            df[f"market_std_{w}d"] = roll_std
            df[f"market_zscore_{w}d"] = z_score
            df[f"market_sma_{w}d_missing"] = roll_mean.isna()

        # 6. Relative Strength Index (RSI)
        rsi_window = self.config.rsi_window
        delta = adj_close.diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)

        # Standard Wilder's exponential smoothing for RSI
        avg_gain = gain.ewm(alpha=1.0 / rsi_window, min_periods=rsi_window, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1.0 / rsi_window, min_periods=rsi_window, adjust=False).mean()

        rs = np.where(avg_loss > 0, avg_gain / avg_loss, np.nan)
        rsi = np.where(
            avg_loss == 0,
            np.where(avg_gain == 0, 50.0, 100.0),
            100.0 - (100.0 / (1.0 + rs))
        )
        # Ensure missing values for initial lookback
        rsi = np.where(avg_gain.isna() | avg_loss.isna(), np.nan, rsi)

        df[f"market_rsi_{rsi_window}d"] = rsi
        df[f"market_rsi_{rsi_window}d_missing"] = np.isnan(rsi)

        # 7. Volume Dynamics & Indicators (guarded against 0 or negative volume division)
        prior_vol = volume.shift(1)
        vol_change_1d = np.where(prior_vol > 0, (volume - prior_vol) / prior_vol, np.nan)
        vol_w = self.config.volume_window
        roll_vol_mean = volume.rolling(window=vol_w, min_periods=vol_w).mean()
        vol_ratio = np.where(roll_vol_mean > 0, volume / roll_vol_mean, np.nan)

        df["market_volume_change_1d"] = vol_change_1d
        df[f"market_volume_sma_{vol_w}d"] = roll_vol_mean
        df[f"market_volume_ratio_{vol_w}d"] = vol_ratio
        df["market_volume_change_1d_missing"] = np.isnan(vol_change_1d)
        df[f"market_volume_ratio_{vol_w}d_missing"] = np.isnan(vol_ratio)

        # 8. Decision Timestamp Attachment
        df = self._attach_decision_timestamps(df)

        return df

    def _attach_decision_timestamps(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Attaches exact, timezone-aware decision cutoff timestamps using MarketCalendar.
        - MARKET_CLOSE: Exact US exchange close converted to UTC (respects EDT/EST and early closes).
        - NEXT_SESSION_OPEN: Next active trading day 09:30 ET open converted to UTC (skips weekends/holidays).
        """
        unique_dates = df["trading_date"].unique()
        date_to_decision = {}

        for d in unique_dates:
            d_str = str(d)[:10]
            if self.config.decision_timing == DecisionTimingMode.MARKET_CLOSE:
                date_to_decision[d] = MarketCalendar.get_session_close_utc(d_str)
            elif self.config.decision_timing == DecisionTimingMode.NEXT_SESSION_OPEN:
                buffer_m = getattr(self.config, "pre_open_cutoff_minutes", 0)
                if buffer_m > 0:
                    date_to_decision[d] = MarketCalendar.get_next_session_open_cutoff_utc(d_str, buffer_minutes=buffer_m)
                else:
                    date_to_decision[d] = MarketCalendar.get_next_session_open_utc(d_str)
            else:
                date_to_decision[d] = MarketCalendar.get_session_close_utc(d_str)

        df["decision_timestamp"] = df["trading_date"].map(date_to_decision)
        df["feature_timing_mode"] = self.config.decision_timing.value
        return df

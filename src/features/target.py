"""
Forward-Return Target Engine.

Calculates leakage-free forward total return prediction targets across
specified holding horizons (e.g. 5-session holding return).

Contract Definitions:
- Decision Timestamp (T): e.g. Session T market close.
- Feasible Executable Entry: Session T+1 opening auction (P_{T+1, open}).
- Feasible Executable Exit: Session T+H market close (P_{T+H, close}).
- Forward Return Target (y_T^(H)):
    y_T^(H) = (P_{T+H, close}^adj - P_{T+1, open}^adj) / P_{T+1, open}^adj

Guarantees:
- Split & dividend adjusted total return via verified adjustment factors.
- Explicit masking of terminal horizon rows where future exit price is unavailable.
- Strict ordering and deduplication per company.
- Future prices are NEVER used as model features; used exclusively to generate target labels.
"""

from dataclasses import dataclass
from typing import Optional, List, Tuple
import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class TargetIntegrityError(Exception):
    """Raised when data structure or pricing violates target construction invariants."""
    pass


@dataclass
class TargetConfig:
    """Configuration for forward return target computation."""
    horizon_sessions: int = 5
    allow_derived_adjusted_open: bool = True
    target_column_name: str = "target_forward_return_5d"
    target_valid_column_name: str = "target_forward_return_5d_valid"


class ForwardReturnTargetEngine:
    """Computes leakage-safe forward return targets using verified adjusted price conventions."""

    REQUIRED_COLUMNS = ["company_id", "trading_date", "open", "close", "adjusted_close"]

    def __init__(self, config: Optional[TargetConfig] = None):
        self.config = config or TargetConfig()

    def add_target(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Computes forward return targets for each company series in df.
        
        :param df: DataFrame containing required market columns.
        :return: DataFrame with added target column and validity indicator.
        """
        if df.empty:
            return df.copy()

        # 1. Validate required columns
        missing = [c for c in self.REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise TargetIntegrityError(f"Market DataFrame missing required columns for target engine: {missing}")

        result_dfs = []
        for cid, grp in df.groupby("company_id", sort=False):
            processed_grp = self._compute_company_target(grp.copy())
            result_dfs.append(processed_grp)

        return pd.concat(result_dfs, axis=0).reset_index(drop=True)

    def _compute_company_target(self, df_comp: pd.DataFrame) -> pd.DataFrame:
        """Computes target for a single company time series."""
        # Check duplicates
        if df_comp["trading_date"].duplicated().any():
            dups = df_comp["trading_date"][df_comp["trading_date"].duplicated()].tolist()
            raise TargetIntegrityError(f"Duplicate trading dates found for company {df_comp['company_id'].iloc[0]}: {dups[:5]}")

        # Ensure chronological ordering
        df_sorted = df_comp.sort_values("trading_date").reset_index(drop=True)

        # Validate non-zero, positive prices
        price_cols = ["open", "close", "adjusted_close"]
        for col in price_cols:
            if (df_sorted[col] <= 0).any() or df_sorted[col].isna().any():
                bad_idx = df_sorted[(df_sorted[col] <= 0) | df_sorted[col].isna()].index.tolist()
                raise TargetIntegrityError(f"Invalid non-positive or null price detected in column {col} at indices: {bad_idx[:5]}")

        # Resolve adjusted open
        adj_open = self._resolve_adjusted_open(df_sorted)
        adj_close = df_sorted["adjusted_close"]

        H = self.config.horizon_sessions
        N = len(df_sorted)

        # Vectorized target calculation:
        # Entry price is adjusted open at T+1: shift(-1)
        # Exit price is adjusted close at T+H: shift(-H)
        entry_price = adj_open.shift(-1)
        exit_price = adj_close.shift(-H)

        target_return = (exit_price - entry_price) / entry_price
        target_valid = target_return.notna() & np.isfinite(target_return)

        # Explicitly verify terminal horizon rows
        # The last H rows must have target_valid == False because exit_price is unavailable
        if N >= H:
            target_valid.iloc[N - H:] = False
            target_return.iloc[N - H:] = np.nan

        df_sorted[self.config.target_column_name] = target_return
        df_sorted[self.config.target_valid_column_name] = target_valid

        # Record entry and exit dates for full auditability
        df_sorted["target_entry_date"] = df_sorted["trading_date"].shift(-1)
        df_sorted["target_exit_date"] = df_sorted["trading_date"].shift(-H)

        return df_sorted

    def _resolve_adjusted_open(self, df: pd.DataFrame) -> pd.Series:
        """
        Extracts or derives split- and dividend-adjusted open price.
        If 'adjusted_open' is present and valid, uses it directly.
        Otherwise, derives via documented adjustment factor:
            factor = adjusted_close / close
            adjusted_open = open * factor
        """
        if "adjusted_open" in df.columns and df["adjusted_open"].notna().all() and (df["adjusted_open"] > 0).all():
            return df["adjusted_open"]

        if not self.config.allow_derived_adjusted_open:
            raise TargetIntegrityError(
                "Column 'adjusted_open' is missing or contains nulls, and allow_derived_adjusted_open is False."
            )

        # Compute CRSP/Yahoo style adjustment factor
        adj_factor = df["adjusted_close"] / df["close"]
        derived_adj_open = df["open"] * adj_factor
        return derived_adj_open

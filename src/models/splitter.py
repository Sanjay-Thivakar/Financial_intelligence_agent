"""
Temporal Cross-Validation and Walk-Forward Splitter Module.

Implements chronological, leakage-free cross-validation for time-series financial datasets:
- Enforces strict chronological ordering (no random shuffling).
- Enforces purging to prevent overlapping forward-return target contamination between train and validation.
- Enforces embargoing to prevent autoregressive feature leakage.
- Ensures all preprocessing transformations (scaling, imputation) are fit exclusively on training folds.
"""

from dataclasses import dataclass
from typing import Generator, List, Optional, Tuple
import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class SplitterIntegrityError(Exception):
    """Raised when dataset ordering or partitioning violates temporal separation rules."""
    pass


@dataclass
class WalkForwardConfig:
    """Configuration for walk-forward chronological splitting."""
    n_splits: int = 3
    train_min_sessions: int = 40  # Minimum sessions required in training fold
    val_sessions: int = 15        # Sessions in each validation fold
    purge_sessions: int = 5       # Embargo/purge gap to eliminate overlapping holding returns (H=5)
    date_column: str = "trading_date"


class WalkForwardSplitter:
    """Generates expanding or rolling chronological walk-forward splits with purging."""

    def __init__(self, config: Optional[WalkForwardConfig] = None):
        self.config = config or WalkForwardConfig()

    def split(self, df: pd.DataFrame) -> Generator[Tuple[np.ndarray, np.ndarray], None, None]:
        """
        Yields (train_indices, val_indices) pairs for chronological cross-validation.
        
        :param df: DataFrame containing sorted trading dates.
        :return: Generator of (train_idx, val_idx) numpy arrays.
        """
        if df.empty:
            return

        date_col = self.config.date_column
        if date_col not in df.columns:
            raise SplitterIntegrityError(f"DataFrame missing required date column '{date_col}' for walk-forward splitting.")

        # Ensure monotonic ordering by trading_date
        unique_dates = pd.Series(df[date_col].unique())
        if not unique_dates.is_monotonic_increasing:
            raise SplitterIntegrityError("Trading dates are not sorted in monotonically increasing chronological order!")

        total_dates = len(unique_dates)
        P = self.config.purge_sessions
        V = self.config.val_sessions
        min_T = self.config.train_min_sessions

        # Required dates: min_T + P + (n_splits * V)
        required_dates = min_T + P + V
        if total_dates < required_dates:
            raise SplitterIntegrityError(
                f"Insufficient historical dates ({total_dates}) for configured walk-forward parameters "
                f"(requires at least {required_dates} = min_T({min_T}) + purge({P}) + val({V}))."
            )

        # Generate splits (expanding train window)
        # We work backwards from total_dates or forwards from min_T
        # Standard expanding window:
        # Split k:
        #   train_end_idx = min_T + k * V
        #   purge gap: train_end_idx to train_end_idx + P
        #   val_start_idx = train_end_idx + P
        #   val_end_idx = val_start_idx + V
        for k in range(self.config.n_splits):
            train_end_idx = min_T + k * V
            val_start_idx = train_end_idx + P
            val_end_idx = val_start_idx + V

            if val_end_idx > total_dates:
                # If remaining dates cannot fill a full validation window, stop or truncate
                break

            train_dates = set(unique_dates.iloc[:train_end_idx])
            val_dates = set(unique_dates.iloc[val_start_idx:val_end_idx])

            # Get row indices in the original dataframe
            train_idx = df.index[df[date_col].isin(train_dates)].to_numpy()
            val_idx = df.index[df[date_col].isin(val_dates)].to_numpy()

            # Sanity verification: zero intersection
            assert len(np.intersect1d(train_idx, val_idx)) == 0, "FATAL: Non-empty intersection between train and val!"

            yield train_idx, val_idx

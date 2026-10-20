"""
License-Safe Feature Storage Controller.

Enforces storage policy constraints on feature datasets before persisting
to disk. Rejects unauthorized persistent storage of commercial vendor data
and guarantees ephemeral in-memory execution when required.
"""

import logging
from pathlib import Path
from typing import Optional, Tuple
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.data.market.storage_policy import DataLayer, LicenseStatus, StoragePolicy
from src.features.config import FeatureStorageConfig, PersistenceMode

logger = logging.getLogger(__name__)


class StorageAuthorizationError(PermissionError):
    """Raised when an attempt is made to persist derived features without verified authorization."""
    pass


class FeatureStorageManager:
    """Manages the persistence or ephemeral retention of derived feature DataFrames."""

    def __init__(self, config: Optional[FeatureStorageConfig] = None):
        self.config = config or FeatureStorageConfig()

    def handle_features(
        self,
        df_features: pd.DataFrame,
        filename: str = "features.parquet",
    ) -> Tuple[bool, Optional[Path], str]:
        """
        Processes feature output according to storage governance rules.
        :param df_features: Aligned feature DataFrame.
        :param filename: Desired filename if saved to disk.
        :return: (is_persisted, file_path_if_saved, status_message)
        """
        # Mode 1: In-Memory (Safe default; avoids persistent disk writes)
        if self.config.persistence_mode == PersistenceMode.IN_MEMORY:
            msg = (
                "In-Memory Mode: Features retained in volatile RAM. "
                "No persistent disk files written. Provider storage authorization remains UNVERIFIED."
            )
            logger.info(msg)
            return False, None, msg

        # Mode 2: Disk Parquet
        # Check explicit user authorization first
        if not self.config.storage_authorized:
            err_msg = (
                "STORAGE REJECTED: storage_authorized is FALSE. "
                "Persistent archiving of derived market features is blocked until explicitly authorized."
            )
            logger.warning(err_msg)
            raise StorageAuthorizationError(err_msg)

        # Evaluate legal rights via StoragePolicy
        is_legal = StoragePolicy.can_persist_locally(
            provider=self.config.provider,
            layer=DataLayer.DERIVED_FEATURES,
            plan_tier=self.config.plan_tier,
        )
        status, reason = StoragePolicy.evaluate_storage_request(
            provider=self.config.provider,
            layer=DataLayer.DERIVED_FEATURES,
            plan_tier=self.config.plan_tier,
        )

        if not is_legal:
            err_msg = (
                f"STORAGE PROHIBITED: {self.config.provider} ({self.config.plan_tier}) "
                f"disallows local feature archiving: {reason}"
            )
            logger.warning(err_msg)
            raise StorageAuthorizationError(err_msg)

        # Output directory setup
        out_dir = self.config.output_dir or Path("data/features")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / filename

        # Write to Parquet using PyArrow
        table = pa.Table.from_pandas(df_features, preserve_index=False)
        pq.write_table(table, str(out_path), compression="snappy")

        success_msg = (
            f"Features persisted to {out_path} under verified {self.config.provider} "
            f"({self.config.plan_tier}) authorization ({len(df_features)} records)."
        )
        logger.info(success_msg)
        return True, out_path, success_msg

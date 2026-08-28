"""Storage for computed feature datasets (Parquet)."""

import pandas as pd
from pathlib import Path
from typing import Optional
from quantos.config import get_config
from quantos.logging import get_logger

logger = get_logger(__name__)


class FeatureStore:
    """
    Save and load feature DataFrames to/from Parquet files.

    Features are stored per symbol and version in a separate directory.
    """

    def __init__(self, base_dir: Optional[Path] = None):
        self.config = get_config()
        self.base_dir = base_dir or self.config.data.parquet_dir
        self.features_dir = self.base_dir / "features"
        self.features_dir.mkdir(parents=True, exist_ok=True)

    def _feature_path(self, symbol: str, version: str) -> Path:
        return self.features_dir / f"{symbol}_{version}.parquet"

    def save_features(self, df_features: pd.DataFrame, symbol: str, version: str) -> int:
        if df_features.empty:
            logger.warning("No features to save.")
            return 0
        path = self._feature_path(symbol, version)
        df_features.to_parquet(path, index=False)
        logger.info(f"Saved {len(df_features)} feature rows to {path}")
        return len(df_features)

    def load_features(self, symbol: str, version: str) -> pd.DataFrame:
        path = self._feature_path(symbol, version)
        if not path.exists():
            return pd.DataFrame()
        return pd.read_parquet(path)

    def list_available(self) -> list:
        files = self.features_dir.glob("*.parquet")
        result = []
        for f in files:
            stem = f.stem
            if "_" in stem:
                parts = stem.split("_", 1)
                if len(parts) == 2:
                    result.append((parts[0], parts[1]))
        return result
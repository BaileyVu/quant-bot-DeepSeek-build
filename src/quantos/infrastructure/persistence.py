"""Parquet storage and retrieval."""

import pandas as pd
from pathlib import Path
from typing import List, Optional
from datetime import datetime
from quantos.domain.candle import Candle
from quantos.config import get_config
from quantos.logging import get_logger

logger = get_logger(__name__)

def candles_to_dataframe(candles: List[Candle]) -> pd.DataFrame:
    """Convert list of Candle to pandas DataFrame with columns."""
    records = [c.dict() for c in candles]
    df = pd.DataFrame(records)
    # Ensure timestamp is datetime
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df

def dataframe_to_candles(df: pd.DataFrame) -> List[Candle]:
    """Convert DataFrame back to Candle objects."""
    candles = []
    for _, row in df.iterrows():
        c = Candle(
            symbol=row["symbol"],
            interval=row["interval"],
            timestamp=row["timestamp"].to_pydatetime(),
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            volume=row["volume"],
            close_time=row.get("close_time"),
        )
        candles.append(c)
    return candles

class ParquetStore:
    def __init__(self, base_dir: Optional[Path] = None):
        config = get_config()
        self.base_dir = base_dir or config.data.parquet_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _symbol_path(self, symbol: str) -> Path:
        return self.base_dir / f"{symbol}.parquet"

    def append_candles(self, candles: List[Candle]) -> None:
        """Append new candles to existing parquet file, or create if missing."""
        if not candles:
            return
        df_new = candles_to_dataframe(candles)
        sym = candles[0].symbol
        path = self._symbol_path(sym)
        if path.exists():
            df_existing = pd.read_parquet(path)
            # Combine and deduplicate by timestamp
            df_all = pd.concat([df_existing, df_new], ignore_index=True)
            df_all = df_all.drop_duplicates(subset=["symbol", "interval", "timestamp"], keep="last")
            df_all = df_all.sort_values("timestamp")
        else:
            df_all = df_new.sort_values("timestamp")
        df_all.to_parquet(path, index=False)
        logger.info(f"Stored {len(candles)} candles for {sym}")

    def read_candles(
        self,
        symbol: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[Candle]:
        path = self._symbol_path(symbol)
        if not path.exists():
            return []
        df = pd.read_parquet(path)
        if start_time:
            df = df[df["timestamp"] >= start_time]
        if end_time:
            df = df[df["timestamp"] <= end_time]
        return dataframe_to_candles(df)
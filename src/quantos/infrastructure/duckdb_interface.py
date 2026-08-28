"""DuckDB analytical query interface over Parquet files."""

import duckdb
from pathlib import Path
from typing import List, Optional
from datetime import datetime
import pandas as pd
from quantos.config import get_config
from quantos.logging import get_logger

logger = get_logger(__name__)

class DuckDBInterface:
    def __init__(self, parquet_dir: Optional[Path] = None):
        self.config = get_config()
        self.parquet_dir = parquet_dir or self.config.data.parquet_dir
        self.conn = duckdb.connect(":memory:")
        self._register_tables()

    def _register_tables(self):
        """Register Parquet files as views."""
        parquet_files = list(self.parquet_dir.glob("*.parquet"))
        if not parquet_files:
            logger.warning("No Parquet files found in data dir")
            return
        # Create a view that reads all parquet files
        # We can also register each symbol individually if needed
        self.conn.execute(
            f"""
            CREATE OR REPLACE VIEW candles AS
            SELECT * FROM read_parquet({[str(p) for p in parquet_files]})
            """
        )

    def query(self, sql: str) -> pd.DataFrame:
        """Execute SQL and return DataFrame."""
        return self.conn.execute(sql).df()

    def get_candles(
        self,
        symbol: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> pd.DataFrame:
        sql = f"SELECT * FROM candles WHERE symbol = '{symbol}'"
        if start_time:
            sql += f" AND timestamp >= '{start_time.isoformat()}'"
        if end_time:
            sql += f" AND timestamp <= '{end_time.isoformat()}'"
        sql += " ORDER BY timestamp"
        return self.query(sql)

    def get_latest_candle(self, symbol: str) -> Optional[pd.Series]:
        df = self.query(
            f"SELECT * FROM candles WHERE symbol = '{symbol}' ORDER BY timestamp DESC LIMIT 1"
        )
        if df.empty:
            return None
        return df.iloc[0]
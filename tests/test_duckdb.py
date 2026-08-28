import pytest
from quantos.infrastructure.duckdb_interface import DuckDBInterface
from quantos.infrastructure.persistence import ParquetStore
from datetime import datetime
from decimal import Decimal
from quantos.domain.candle import Candle

def test_duckdb_query(tmp_path):
    # store some data first
    store = ParquetStore(base_dir=tmp_path)
    c1 = Candle(symbol="BTCUSDT", interval="1m", timestamp=datetime(2025,1,1,0,0),
                open=100, high=101, low=99, close=100.5, volume=10)
    store.append_candles([c1])
    db = DuckDBInterface(parquet_dir=tmp_path)
    df = db.get_candles("BTCUSDT")
    assert len(df) == 1
    df_latest = db.get_latest_candle("BTCUSDT")
    assert df_latest is not None
    assert df_latest["symbol"] == "BTCUSDT"
import pytest
import pandas as pd
from pathlib import Path
from quantos.infrastructure.persistence import ParquetStore, candles_to_dataframe
from quantos.domain.candle import Candle
from datetime import datetime
from decimal import Decimal

def test_parquet_store(tmp_path):
    store = ParquetStore(base_dir=tmp_path)
    c1 = Candle(symbol="BTCUSDT", interval="1m", timestamp=datetime(2025,1,1,0,0),
                open=100, high=101, low=99, close=100.5, volume=10)
    store.append_candles([c1])
    assert (tmp_path / "BTCUSDT.parquet").exists()
    df = pd.read_parquet(tmp_path / "BTCUSDT.parquet")
    assert len(df) == 1
    # read back
    candles = store.read_candles("BTCUSDT")
    assert len(candles) == 1
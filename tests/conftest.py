import pytest
from pathlib import Path
from quantos.config import Config

@pytest.fixture
def sample_candle_data():
    from quantos.domain.candle import Candle
    from datetime import datetime
    return Candle(
        symbol="BTCUSDT",
        interval="1m",
        timestamp=datetime(2025, 1, 1, 0, 0, 0),
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=10.0,
    )

@pytest.fixture
def test_config_path(tmp_path):
    config_content = """
symbols:
  - BTCUSDT
interval: "1m"
initial_capital: 20.0
data:
  parquet_dir: "./data/parquet"
logging:
  level: "DEBUG"
"""
    p = tmp_path / "config.yaml"
    p.write_text(config_content)
    return p
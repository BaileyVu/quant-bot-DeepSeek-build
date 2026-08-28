from datetime import datetime
from decimal import Decimal
import pytest
from quantos.domain.candle import Candle

def test_candle_valid(sample_candle_data):
    assert sample_candle_data.symbol == "BTCUSDT"
    assert sample_candle_data.open == Decimal(100.0)

def test_candle_invalid_high_lt_low():
    with pytest.raises(ValueError, match="high must be >= low"):
        Candle(
            symbol="BTCUSDT",
            interval="1m",
            timestamp=datetime.now(),
            open=100,
            high=99,
            low=101,
            close=100,
            volume=10,
        )

def test_candle_close_out_of_bounds():
    with pytest.raises(ValueError, match="close must be between low and high"):
        Candle(
            symbol="BTCUSDT",
            interval="1m",
            timestamp=datetime.now(),
            open=100,
            high=101,
            low=99,
            close=102,
            volume=10,
        )
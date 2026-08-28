from datetime import datetime, timedelta
from decimal import Decimal
import pytest
from quantos.market_data.validator import (
    validate_candle,
    normalize_binance_kline,
    detect_duplicates,
    detect_missing_candles,
)
from quantos.domain.candle import Candle

def test_validate_good_candle(sample_candle_data):
    assert validate_candle(sample_candle_data) is True

def test_validate_bad_timestamp():
    c = Candle(
        symbol="BTCUSDT",
        interval="1m",
        timestamp=datetime(2025,1,1,0,0,30),  # not on minute
        open=100, high=101, low=99, close=100.5, volume=10
    )
    assert validate_candle(c) is False

def test_normalize_binance():
    raw = [1704067200000, "100.0", "101.0", "99.0", "100.5", "10.0", 1704067260000, "0", "0", "0", "0", "0"]
    c = normalize_binance_kline(raw, "BTCUSDT", "1m")
    assert c.timestamp == datetime(2024,1,1,0,0)  # adjust actual year? Use correct.
    # We'll update to realistic: 1704067200000 is 2024-01-01 00:00:00 UTC
    assert c.symbol == "BTCUSDT"

def test_detect_duplicates():
    c1 = Candle(symbol="BTC", interval="1m", timestamp=datetime(2025,1,1,0,0), open=100, high=101, low=99, close=100, volume=1)
    c2 = Candle(symbol="BTC", interval="1m", timestamp=datetime(2025,1,1,0,0), open=100, high=101, low=99, close=100, volume=1)
    unique = detect_duplicates([c1, c2])
    assert len(unique) == 1

def test_detect_missing_candles():
    base = datetime(2025,1,1,0,0)
    c1 = Candle(symbol="BTC", interval="1m", timestamp=base, open=1, high=2, low=0, close=1, volume=1)
    c2 = Candle(symbol="BTC", interval="1m", timestamp=base + timedelta(minutes=2), open=1, high=2, low=0, close=1, volume=1)
    missing = detect_missing_candles([c1, c2])
    assert len(missing) == 1
    assert missing[0] == base + timedelta(minutes=1)
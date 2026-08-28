"""Candle validation and normalization."""

from datetime import datetime, timedelta
from typing import List, Set
from decimal import Decimal
from quantos.domain.candle import Candle
from quantos.logging import get_logger

logger = get_logger(__name__)

def validate_candle(candle: Candle) -> bool:
    """Runs pydantic validation, catches errors."""
    try:
        # pydantic already validates on creation, but we also check extra rules
        # e.g., ensure timestamp is on minute boundary
        if candle.timestamp.second != 0 or candle.timestamp.microsecond != 0:
            raise ValueError("timestamp must be at start of minute")
        # interval must be '1m' for V1
        if candle.interval != "1m":
            raise ValueError("only '1m' interval supported")
        # check volume > 0? maybe allow zero, but we'll warn
        if candle.volume < 0:
            raise ValueError("volume cannot be negative")
        return True
    except Exception as e:
        logger.error(f"Invalid candle: {candle} - {e}")
        return False

def normalize_binance_kline(raw: List, symbol: str, interval: str) -> Candle:
    """
    Convert Binance kline list to Candle.
    Expected format: [openTime, open, high, low, close, volume, closeTime, ...]
    """
    open_time = datetime.fromtimestamp(raw[0] / 1000.0)
    close_time = datetime.fromtimestamp(raw[6] / 1000.0)
    return Candle(
        symbol=symbol,
        interval=interval,
        timestamp=open_time,
        open=Decimal(raw[1]),
        high=Decimal(raw[2]),
        low=Decimal(raw[3]),
        close=Decimal(raw[4]),
        volume=Decimal(raw[5]),
        close_time=close_time,
    )

def detect_duplicates(candles: List[Candle]) -> List[Candle]:
    """Remove duplicates based on (symbol, interval, timestamp)."""
    seen: Set[tuple] = set()
    unique = []
    for c in candles:
        key = (c.symbol, c.interval, c.timestamp)
        if key not in seen:
            seen.add(key)
            unique.append(c)
        else:
            logger.warning(f"Duplicate candle discarded: {c}")
    return unique

def detect_missing_candles(candles: List[Candle]) -> List[datetime]:
    """
    Given a sorted list of candles (by timestamp), detect missing minutes.
    Returns list of missing timestamps.
    """
    if not candles:
        return []
    missing = []
    # Ensure sorted
    sorted_candles = sorted(candles, key=lambda c: c.timestamp)
    start = sorted_candles[0].timestamp
    end = sorted_candles[-1].timestamp
    current = start
    idx = 0
    while current <= end:
        if idx < len(sorted_candles) and sorted_candles[idx].timestamp == current:
            idx += 1
        else:
            missing.append(current)
        current += timedelta(minutes=1)
    return missing
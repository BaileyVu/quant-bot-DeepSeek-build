"""Core domain: Candle."""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field, validator

class Candle(BaseModel):
    symbol: str
    interval: str  # e.g., "1m"
    timestamp: datetime  # UTC, start of the minute
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    close_time: Optional[datetime] = None  # optional, derived

    @validator("open", "high", "low", "close", "volume")
    def non_negative(cls, v):
        if v < 0:
            raise ValueError("Price/volume must be non-negative")
        return v

    @validator("high")
    def high_ge_low(cls, v, values):
        low = values.get("low")
        if low is not None and v < low:
            raise ValueError("high must be >= low")
        return v

    @validator("close")
    def close_between(cls, v, values):
        low = values.get("low")
        high = values.get("high")
        if low is not None and high is not None and not (low <= v <= high):
            raise ValueError("close must be between low and high")
        return v

    @validator("open")
    def open_between(cls, v, values):
        low = values.get("low")
        high = values.get("high")
        if low is not None and high is not None and not (low <= v <= high):
            raise ValueError("open must be between low and high")
        return v

    class Config:
        allow_mutation = False
        frozen = True
"""Dataset helpers for backtests."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, List

import numpy as np

from ..data import Bar
from ..utils.time import utc_now


@dataclass
class HistoricalData:
    bars: List[Bar]


def synthetic_dataset(symbol: str, interval: str, periods: int = 500) -> HistoricalData:
    base = utc_now() - timedelta(minutes=periods)
    price = 30_000.0
    bars: list[Bar] = []
    rng = np.random.default_rng(123)
    for i in range(periods):
        open_time = base + timedelta(minutes=i)
        ret = rng.normal(0, 0.0005)
        close = price * (1 + ret)
        high = max(price, close) * (1 + rng.normal(0, 0.0002))
        low = min(price, close) * (1 - rng.normal(0, 0.0002))
        volume = 100 + abs(ret) * 10_000
        bars.append(Bar(symbol=symbol, open_time=open_time, open=price, high=high, low=low, close=close, volume=volume))
        price = close
    return HistoricalData(bars=bars)


__all__ = ["HistoricalData", "synthetic_dataset"]

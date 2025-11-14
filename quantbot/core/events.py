"""Core event model shared by backtest, paper, and live execution."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from datetime import datetime

from ..data import Bar, MarketState

OrderSide = Literal["buy", "sell"]
OrderType = Literal["market", "limit", "post_only"]


@dataclass(slots=True)
class MarketEvent:
    symbol: str
    state: MarketState
    timestamp: datetime
    bar: Bar | None = None
    sequence: int = 0


@dataclass(slots=True)
class SignalEvent:
    strategy_id: str
    symbol: str
    target_qty: float
    timestamp: datetime
    metadata: dict[str, float] | None = None


@dataclass(slots=True)
class OrderRequest:
    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType
    price: float | None = None
    reduce_only: bool = False
    post_only: bool = False
    client_order_id: str | None = None


@dataclass(slots=True)
class OrderEvent:
    request: OrderRequest
    order_id: str
    timestamp: datetime


@dataclass(slots=True)
class FillEvent:
    order_id: str
    symbol: str
    price: float
    quantity: float
    fee: float
    side: OrderSide
    timestamp: datetime


@dataclass(slots=True)
class ReplayEvent:
    """Persisted event used for replay."""

    type: str
    payload: dict
    timestamp: datetime

    def to_json(self) -> dict:
        return {
            "type": self.type,
            "timestamp": self.timestamp.isoformat(),
            "payload": self.payload,
        }


__all__ = [
    "MarketEvent",
    "SignalEvent",
    "OrderRequest",
    "OrderEvent",
    "FillEvent",
    "ReplayEvent",
    "OrderSide",
    "OrderType",
]

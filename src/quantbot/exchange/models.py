"""Common exchange-side data models."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


Side = Literal["buy", "sell"]
OrderType = Literal["market", "limit", "stop_market", "stop_limit"]


@dataclass(slots=True)
class SymbolMeta:
    symbol: str
    price_precision: int
    size_precision: int
    tick_size: float
    step_size: float
    min_notional: float
    max_leverage: float

    def quantize_price(self, price: float) -> float:
        factor = 10**self.price_precision
        return round(price * factor) / factor

    def quantize_size(self, size: float) -> float:
        factor = 10**self.size_precision
        return round(size * factor) / factor

    def enforce_min_notional(self, size: float, price: float) -> None:
        if abs(size * price) < self.min_notional:
            raise ValueError(
                f"order notional {abs(size * price):.4f} below min notional {self.min_notional:.4f}"
            )


@dataclass(slots=True)
class OrderRequest:
    symbol: str
    side: Side
    type: OrderType
    qty: float
    price: float | None = None
    reduce_only: bool = False
    client_order_id: str | None = None


@dataclass(slots=True)
class PlacedOrder:
    order_id: str
    symbol: str
    side: Side
    type: OrderType
    qty: float
    price: float | None
    status: Literal["open", "filled", "cancelled", "rejected"]
    client_order_id: str | None = None
    meta: dict[str, float | str] = field(default_factory=dict)


@dataclass(slots=True)
class Position:
    symbol: str
    qty: float
    entry_price: float
    unrealized_pnl: float = 0.0
    leverage: float = 1.0


@dataclass(slots=True)
class AccountState:
    equity: float
    available_balance: float
    timestamp: datetime
    margin_ratio: float | None = None


__all__ = [
    "SymbolMeta",
    "OrderRequest",
    "PlacedOrder",
    "Position",
    "AccountState",
    "Side",
    "OrderType",
]

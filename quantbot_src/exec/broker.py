"""Broker abstraction."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class Order:
    symbol: str
    side: str
    qty: float
    price: float | None
    order_type: str


class Broker(Protocol):
    async def create_order(self, order: Order) -> dict:
        ...

    async def cancel_order(self, order_id: str) -> None:
        ...

    async def query_position(self, symbol: str) -> dict:
        ...

    @property
    def taker_fee_bps(self) -> float:
        ...

    @property
    def maker_fee_bps(self) -> float:
        ...


class PaperBroker:
    """Simulated broker for paper trading."""

    def __init__(self, maker_fee_bps: float, taker_fee_bps: float) -> None:
        self._maker_fee_bps = maker_fee_bps
        self._taker_fee_bps = taker_fee_bps
        self.orders: list[dict] = []
        self.position = 0.0
        self.avg_price = 0.0

    @property
    def taker_fee_bps(self) -> float:
        return self._taker_fee_bps

    @property
    def maker_fee_bps(self) -> float:
        return self._maker_fee_bps

    async def create_order(self, order: Order) -> dict:
        fill_price = order.price or 0.0
        side = 1 if order.side.lower() == "buy" else -1
        new_qty = self.position + order.qty * side
        self.position = new_qty
        self.avg_price = fill_price if new_qty != 0 else 0.0
        trade = {
            "symbol": order.symbol,
            "qty": order.qty * side,
            "price": fill_price,
            "side": order.side,
            "type": order.order_type,
        }
        self.orders.append(trade)
        return trade

    async def cancel_order(self, order_id: str) -> None:  # pragma: no cover - noop
        return None

    async def query_position(self, symbol: str) -> dict:
        return {"symbol": symbol, "qty": self.position, "avg_price": self.avg_price}


__all__ = ["Broker", "Order", "PaperBroker"]

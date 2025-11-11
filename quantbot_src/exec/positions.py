"""Position reconciliation."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Position:
    symbol: str
    qty: float
    avg_price: float


class PositionTracker:
    def __init__(self) -> None:
        self.position = Position(symbol="", qty=0.0, avg_price=0.0)

    def update(self, symbol: str, fill_qty: float, fill_price: float) -> Position:
        if self.position.symbol != symbol:
            self.position = Position(symbol=symbol, qty=0.0, avg_price=0.0)
        qty = self.position.qty + fill_qty
        if qty == 0:
            avg_price = 0.0
        else:
            pnl_component = self.position.avg_price * self.position.qty + fill_price * fill_qty
            avg_price = pnl_component / qty
        self.position = Position(symbol=symbol, qty=qty, avg_price=avg_price)
        return self.position

    def drift(self, external_qty: float) -> float:
        return self.position.qty - external_qty


__all__ = ["PositionTracker", "Position"]

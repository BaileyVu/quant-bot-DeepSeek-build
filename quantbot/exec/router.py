"""Order routing utilities."""
from __future__ import annotations

from dataclasses import dataclass

from .broker import Broker, Order
from ..data import MarketState


@dataclass
class RouteResult:
    order: Order
    fill: dict


class Router:
    def __init__(self, broker: Broker) -> None:
        self.broker = broker

    async def route_to_target(self, symbol: str, current_qty: float, target_qty: float, state: MarketState) -> RouteResult | None:
        delta = target_qty - current_qty
        if abs(delta) < 1e-8:
            return None
        side = "buy" if delta > 0 else "sell"
        price = state.bid if side == "buy" else state.ask
        order = Order(symbol=symbol, side=side, qty=abs(delta), price=price, order_type="limit")
        fill = await self.broker.create_order(order)
        return RouteResult(order=order, fill=fill)

    async def twap(
        self,
        symbol: str,
        current_qty: float,
        target_qty: float,
        state: MarketState,
        slices: int = 3,
    ) -> list[RouteResult]:
        results: list[RouteResult] = []
        step = (target_qty - current_qty) / slices
        qty = current_qty
        for _ in range(slices):
            qty += step
            result = await self.route_to_target(symbol, qty - step, qty, state)
            if result:
                results.append(result)
        return results


__all__ = ["Router", "RouteResult"]
